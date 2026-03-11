"""
中间件限流集成测试。

覆盖 Type 1（套餐规则）和 Type 2（账户余额）的各种组合场景。
使用 FastAPI TestClient + SQLite 内存数据库 + mock Redis。
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

# 设置测试环境变量（在导入 app 之前）
os.environ["ADMIN_KEY"] = "test-admin-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ.setdefault("ADMIN_FALLBACK_KEY", "fallback-key")

# 使用内存数据库引擎覆盖（StaticPool 保证跨连接共享同一 DB）
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def override_session():
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        yield session


# 导入 app 和相关模块（必须在环境变量设置之后）
from db.database import async_session_generator  # noqa: E402
from db.models import RateLimit, Token, User, UserGroup  # noqa: E402
from gateway import app  # noqa: E402


# ---------------------------------------------------------------------------
# DB 初始化 fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """创建测试数据库表（session 级别，只建一次）。"""

    async def _create():
        import db.models  # noqa: F401 - 确保所有表注册到 metadata

        async with TEST_ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_create())


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """提供测试客户端，覆盖 DB 依赖（包括 middleware 使用的 engine）。"""
    import db.database as _db
    import gateway as _gw
    import middleware.auth as _auth_mw

    original_db_engine = _db.engine
    original_gw_engine = _gw.engine
    _db.engine = TEST_ENGINE
    _gw.engine = TEST_ENGINE
    original_mw_engine = getattr(_auth_mw, "engine", None)
    _auth_mw.engine = TEST_ENGINE

    app.dependency_overrides[async_session_generator] = override_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()

    # 还原 engine
    _db.engine = original_db_engine
    _gw.engine = original_gw_engine
    if original_mw_engine is not None:
        _auth_mw.engine = original_mw_engine


# ---------------------------------------------------------------------------
# 辅助函数：直接写入 TEST_ENGINE（绕过路由，确保隔离）
# ---------------------------------------------------------------------------


def _run(coro):
    """在当前线程运行协程（pytest-asyncio 未启用时使用）。"""
    return asyncio.run(coro)


async def _insert_user(username: str, quota_usd) -> None:
    """插入 User 记录（quota_usd 可为 None、0 或正数）。

    SQLite 的 ORM 写入路径会把 None 转为 0.0（默认值），因此对 None 使用 raw SQL
    写入真实的 NULL 值，确保 check_account_quota(None) 能正确返回 True（无限放行）。
    """
    from sqlalchemy import text

    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        # 幂等：先删除已有记录
        await session.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
        # 插入新记录
        if quota_usd is None:
            await session.execute(
                text(
                    "INSERT INTO users (username, created_at, quota_usd, used_usd)"
                    " VALUES (:u, '2026-01-01Z', NULL, 0)"
                ),
                {"u": username},
            )
        else:
            await session.execute(
                text(
                    "INSERT INTO users (username, created_at, quota_usd, used_usd)"
                    " VALUES (:u, '2026-01-01Z', :q, 0)"
                ),
                {"u": username, "q": quota_usd},
            )
        await session.commit()


async def _insert_group(name: str) -> str:
    """插入 UserGroup，返回 group_id。"""
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        group = UserGroup(name=name)
        session.add(group)
        await session.commit()
        await session.refresh(group)
        return group.id


async def _insert_rate_limit(
    group_id: str, window_sec: int, limit_type: str, value: float
) -> str:
    """插入 RateLimit 规则，返回 id。"""
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        rl = RateLimit(
            group_id=group_id,
            window_sec=window_sec,
            limit_type=limit_type,
            value=value,
        )
        session.add(rl)
        await session.commit()
        await session.refresh(rl)
        return rl.id


async def _insert_token(
    name: str,
    username: str | None = None,
    group_id: str | None = None,
) -> str:
    """插入 Token，返回 key（sk-xxx）。"""
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        token = Token(name=name, username=username, group_id=group_id)
        session.add(token)
        await session.commit()
        await session.refresh(token)
        return token.key


# ---------------------------------------------------------------------------
# 辅助：发送测试请求
# ---------------------------------------------------------------------------

_CHAT_PAYLOAD = {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "hello"}],
}


def _post_chat(client, api_key: str):
    return client.post(
        "/v1/chat/completions",
        json=_CHAT_PAYLOAD,
        headers={"Authorization": f"Bearer {api_key}"},
    )


# ===========================================================================
# 测试场景
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. Type 2：无 group，quota_usd=0（默认）→ 429
# ---------------------------------------------------------------------------


def test_type2_no_group_zero_quota_returns_429(client):
    """无 group 的 token，用户 quota_usd=0 → 429，error 包含 'quota'。"""
    username = "user_zero_quota"
    _run(_insert_user(username, quota_usd=0))
    key = _run(_insert_token("t1_zero", username=username, group_id=None))

    resp = _post_chat(client, key)
    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
    assert "quota" in resp.json().get("error", "").lower()


# ---------------------------------------------------------------------------
# 2. Type 2：无 group，quota_usd=None（无限）→ 放行（非 429）
# ---------------------------------------------------------------------------


def test_type2_no_group_unlimited_quota_passes(client):
    """无 group 的 token，用户 quota_usd=None（无限）→ 不是 429（会因无上游而 502/503）。"""
    username = "user_unlimited"
    _run(_insert_user(username, quota_usd=None))
    key = _run(_insert_token("t2_unlimited", username=username, group_id=None))

    resp = _post_chat(client, key)
    assert resp.status_code != 429, f"should not be 429, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# 3. Type 1：有 group，request_limit，Redis 返回超限 → 429
# ---------------------------------------------------------------------------


def test_type1_request_limit_exceeded_returns_429(client):
    """Type 1 限速规则超限 → 降级 Type 2 也超限（quota_usd=0）→ 429。"""
    username = "user_t1_exceeded"
    _run(_insert_user(username, quota_usd=0))  # Type 2 无余额，最终 429
    group_id = _run(_insert_group("group_req_limit_exceeded"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t3_exceeded", username=username, group_id=group_id))

    # mock get_window_count 返回 1（current >= value=1 → Type 1 超限）
    with patch(
        "services.rate_limit_service.get_window_count", new_callable=AsyncMock
    ) as mock_count:
        mock_count.return_value = 1  # Type 1 超限，降级到 Type 2，Type 2 也无额度
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
    # Type 1 超限后降级到 Type 2，最终 error 来自 Type 2 "quota exceeded"
    body = resp.json().get("error", "")
    assert "quota" in body.lower(), f"error should mention quota, got: {body}"


# ---------------------------------------------------------------------------
# 4. Type 1：有 group，未超限 → 放行（非 429）
# ---------------------------------------------------------------------------


def test_type1_request_limit_not_exceeded_passes(client):
    """Type 1 限速规则未超限（count=0 < value=1）→ 不是 429。"""
    username = "user_t1_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_req_limit_pass"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t4_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_count", new_callable=AsyncMock
    ) as mock_count:
        mock_count.return_value = 0  # current=0 < value=1 → 通过
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"should not be 429, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# 5. Type 1 超限 → Type 2 有余额 → 放行
# ---------------------------------------------------------------------------


def test_type1_exceeded_type2_has_quota_passes(client):
    """Type 1 超限，但用户 quota_usd=50.0（有余额）→ Type 2 放行，不是 429。"""
    username = "user_t1_t2_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_fallback_pass"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t5_fallback_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_count", new_callable=AsyncMock
    ) as mock_count:
        mock_count.return_value = 1  # Type 1 超限
        resp = _post_chat(client, key)

    assert resp.status_code != 429, (
        f"Type 2 has quota, should not be 429, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# 6. Type 1 超限 → Type 2 也超限 → 429
# ---------------------------------------------------------------------------


def test_type1_exceeded_type2_no_quota_returns_429(client):
    """Type 1 超限，用户 quota_usd=0 → Type 2 也超限 → 429。"""
    username = "user_t1_t2_fail"
    _run(_insert_user(username, quota_usd=0))
    group_id = _run(_insert_group("group_fallback_fail"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t6_fallback_fail", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_count", new_callable=AsyncMock
    ) as mock_count:
        mock_count.return_value = 1  # Type 1 超限
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# 7. Redis 不可用 → fail open → 放行
# ---------------------------------------------------------------------------


def test_redis_unavailable_fail_open(client):
    """Redis 不可用（ConnectionError）→ fail open → 不是 429。"""
    username = "user_redis_fail"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_redis_fail"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t7_redis_fail", username=username, group_id=group_id))

    # mock 模块级 _get_redis 函数抛出 ConnectionError，触发 _check_limits 的 fail open
    with patch(
        "middleware.auth._get_redis",
        new_callable=AsyncMock,
        side_effect=ConnectionError("Redis unreachable"),
    ):
        resp = _post_chat(client, key)

    assert resp.status_code != 429, (
        f"Redis fail open should not 429, got {resp.status_code}: {resp.text}"
    )
