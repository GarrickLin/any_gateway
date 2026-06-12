"""测试 /v1/responses 端点：请求转换 → 上游 chat → 响应转换，复用计费/鉴权链路。

上游 httpx 调用被 fake client 拦截，不发起真实网络请求。
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import SQLModel

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

os.environ.setdefault("ADMIN_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# 使用 file-based sqlite：端点的 fire-and-forget 计费 task 会在 TestClient 的
# event loop 关闭时操作 DB，file db 让各 loop 打开各自 connection 互不影响，
# 避免 :memory: + StaticPool 单 connection 被 background task 损坏。
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
ENGINE = create_async_engine(f"sqlite+aiosqlite:///{_TMP_DB.name}")

API_KEY = "sk-resp-test"


@pytest.fixture(scope="module", autouse=True)
def setup():
    import db.database as _db
    original_engine = _db.engine

    async def _run():
        import db.models  # noqa: F401
        async with ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        from db.models import (UserGroup, Channel, User, UserGroupMembership,
                               GroupChannel, Token)
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            g = UserGroup(name="premium", priority=10)
            s.add(g)
            await s.flush()

            c = Channel(name="openai-ch", provider="openai",
                        base_url="http://upstream/v1", api_key="up-key",
                        weight=1, enabled=True, models=json.dumps(["gpt-4o"]))
            s.add(c)
            await s.flush()

            s.add(GroupChannel(group_id=g.id, channel_id=c.id))
            s.add(User(username="alice", quota_usd=100))
            s.add(UserGroupMembership(username="alice", group_id=g.id))
            # 无 group_id 的 Type 2 token，避免触发 Redis 限流检查
            s.add(Token(name="t1", key=API_KEY, username="alice", quota_usd=0))
            await s.commit()

    import db.database as _dbmod
    _dbmod.engine = ENGINE
    import gateway as _gw
    original_gw_engine = _gw.engine
    _gw.engine = ENGINE
    # lifespan 不会在 TestClient(app) 下触发，手动初始化后台任务集合
    _gw.app.state.log_tasks = set()

    # 中间件与计费模块各自 `from db.database import engine`，需同步覆盖
    import middleware.auth as _mw
    import services.quota as _quota
    original_mw_engine = _mw.engine
    original_quota_engine = _quota.engine
    _mw.engine = ENGINE
    _quota.engine = ENGINE

    asyncio.run(_run())
    yield
    _db.engine = original_engine
    _gw.engine = original_gw_engine
    _mw.engine = original_mw_engine
    _quota.engine = original_quota_engine
    asyncio.run(ENGINE.dispose())
    os.unlink(_TMP_DB.name)


# ── Fake 上游 httpx client ────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None, lines=None):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {"content-type": "application/json"}
        self._lines = lines or []

    @property
    def content(self):
        return self._content

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class _FakeAsyncClient:
    preset: _FakeResponse = None  # 由测试设置

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, *a, **k):
        return _FakeAsyncClient.preset

    def stream(self, *a, **k):
        return _FakeStreamCtx(_FakeAsyncClient.preset)


@pytest.fixture
def fake_upstream(monkeypatch):
    import gateway
    monkeypatch.setattr(gateway.httpx, "AsyncClient", _FakeAsyncClient)

    def _set(resp):
        _FakeAsyncClient.preset = resp
    yield _set
    _FakeAsyncClient.preset = None


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import gateway
    return TestClient(gateway.app)


# ── 测试 ──────────────────────────────────────────────────────────────────────

def test_missing_api_key_returns_401(client):
    r = client.post("/v1/responses", json={"model": "gpt-4o", "input": "hi"})
    assert r.status_code == 401


def test_unknown_model_returns_400(client, fake_upstream):
    r = client.post(
        "/v1/responses",
        json={"model": "does-not-exist", "input": "hi"},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert r.status_code == 400


def test_non_stream_returns_responses_format(client, fake_upstream):
    chat_resp = {
        "id": "chatcmpl-1", "object": "chat.completion", "created": 1700000000,
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    fake_upstream(_FakeResponse(200, content=json.dumps(chat_resp).encode()))

    r = client.post(
        "/v1/responses",
        json={"model": "gpt-4o", "input": "hi"},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "response"
    assert data["status"] == "completed"
    assert data["output"][0]["content"][0]["text"] == "Hello!"
    assert data["usage"]["input_tokens"] == 5


def test_stream_returns_responses_event_sequence(client, fake_upstream):
    lines = [
        'data: {"choices":[{"delta":{"role":"assistant","content":"Hi"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}',
        'data: [DONE]',
    ]
    fake_upstream(_FakeResponse(200, lines=lines))

    r = client.post(
        "/v1/responses",
        json={"model": "gpt-4o", "input": "hi", "stream": True},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert r.status_code == 200
    text = r.text
    assert "event: response.created" in text
    assert "event: response.output_text.delta" in text
    assert "event: response.completed" in text


def test_upstream_error_is_passed_through(client, fake_upstream):
    err = {"error": {"message": "bad request", "type": "invalid_request_error"}}
    fake_upstream(_FakeResponse(400, content=json.dumps(err).encode()))

    r = client.post(
        "/v1/responses",
        json={"model": "gpt-4o", "input": "hi"},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "bad request"
