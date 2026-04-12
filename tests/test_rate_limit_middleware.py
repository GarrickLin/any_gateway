"""
中间件限流集成测试。

覆盖 Type 1（套餐规则）和 Type 2（账户余额）的各种组合场景。
使用 FastAPI TestClient + SQLite 内存数据库 + mock Redis。
"""
import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, Session, create_engine

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

# 设置测试环境变量（在导入 app 之前）
os.environ["ADMIN_KEY"] = "test-admin-secret"
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"any_gateway_rate_limit_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("ADMIN_FALLBACK_KEY", "fallback-key")

# 使用临时文件数据库，避免多个 event loop/线程共享同一内存连接。
TEST_ENGINE = create_async_engine(
    f"sqlite+aiosqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
SYNC_TEST_ENGINE = create_engine(
    f"sqlite:///{_TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
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
    import db.models  # noqa: F401 - 确保所有表注册到 metadata

    SQLModel.metadata.create_all(SYNC_TEST_ENGINE)
    yield
    asyncio.run(TEST_ENGINE.dispose())
    SYNC_TEST_ENGINE.dispose()
    _TEST_DB_PATH.unlink(missing_ok=True)


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
    """兼容旧调用风格；仅在传入 awaitable 时才执行 asyncio.run。"""
    if inspect.isawaitable(coro):
        return asyncio.run(coro)
    return coro


def _insert_user(username: str, quota_usd) -> None:
    """插入 User 记录（quota_usd 可为 None、0 或正数）。

    SQLite 的 ORM 写入路径会把 None 转为 0.0（默认值），因此对 None 使用 raw SQL
    写入真实的 NULL 值，确保 check_account_quota(None) 能正确返回 True（无限放行）。
    """
    with Session(SYNC_TEST_ENGINE) as session:
        # 幂等：先删除已有记录
        session.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
        # 插入新记录
        if quota_usd is None:
            session.execute(
                text(
                    "INSERT INTO users (username, created_at, quota_usd, used_usd)"
                    " VALUES (:u, '2026-01-01Z', NULL, 0)"
                ),
                {"u": username},
            )
        else:
            session.execute(
                text(
                    "INSERT INTO users (username, created_at, quota_usd, used_usd)"
                    " VALUES (:u, '2026-01-01Z', :q, 0)"
                ),
                {"u": username, "q": quota_usd},
            )
        session.commit()


def _insert_group(name: str) -> str:
    """插入 UserGroup，返回 group_id。"""
    with Session(SYNC_TEST_ENGINE) as session:
        group = UserGroup(name=name)
        session.add(group)
        session.commit()
        session.refresh(group)
        return group.id


def _insert_rate_limit(
    group_id: str, window_sec: int, limit_type: str, value: float
) -> str:
    """插入 RateLimit 规则，返回 id。"""
    with Session(SYNC_TEST_ENGINE) as session:
        rl = RateLimit(
            group_id=group_id,
            window_sec=window_sec,
            limit_type=limit_type,
            value=value,
        )
        session.add(rl)
        session.commit()
        session.refresh(rl)
        return rl.id


def _insert_token(
    name: str,
    username: str | None = None,
    group_id: str | None = None,
) -> str:
    """插入 Token，返回 key（sk-xxx）。"""
    with Session(SYNC_TEST_ENGINE) as session:
        token = Token(name=name, username=username, group_id=group_id)
        session.add(token)
        session.commit()
        session.refresh(token)
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
    # Type 1 超限后降级到 Type 2，最终 error 应包含 Type 1 的具体超限原因 request_limit
    body = resp.json().get("error", "")
    assert "request_limit" in body.lower(), f"error should mention request_limit, got: {body}"


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
# 5. Type 1：无启用规则 → 回退 Type 2
# ---------------------------------------------------------------------------


def test_type1_without_active_rules_falls_back_to_type2(client):
    """有 group 但没有任何启用规则时，不应标记为套餐，应回退到 Type 2。"""
    username = "user_no_active_rules"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_no_active_rules"))
    key = _run(_insert_token("t_no_active_rules", username=username, group_id=group_id))

    resp = _post_chat(client, key)

    assert resp.status_code != 429, f"Type 2 has quota, should not be 429, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 6. Type 1 超限 → Type 2 有余额 → 放行
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
# 7. Type 1 超限 → Type 2 也超限 → 429
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
    # Type 1 超限后降级到 Type 2，最终 error 应包含 Type 1 的具体超限原因 request_limit
    body = resp.json().get("error", "")
    assert "request_limit" in body.lower(), f"error should mention request_limit, got: {body}"


# ---------------------------------------------------------------------------
# 8. Redis 不可用 → fail open → 放行
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


# ---------------------------------------------------------------------------
# Task 3：token_limit 类型测试
# ---------------------------------------------------------------------------


def test_token_limit_not_exceeded_passes(client):
    """token_limit 规则：窗口内 token 数未超限 → 放行（非 429）。"""
    username = "user_token_limit_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_token_limit_pass"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="token_limit", value=10000))
    key = _run(_insert_token("t_token_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 9000.0  # 9000 < 10000 → 通过
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"should not be 429, got {resp.status_code}: {resp.text}"


def test_token_limit_exceeded_returns_429(client):
    """token_limit 规则：窗口内 token 数超限 → 429，error 包含 token_limit。"""
    username = "user_token_limit_fail"
    _run(_insert_user(username, quota_usd=0))
    group_id = _run(_insert_group("group_token_limit_fail"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="token_limit", value=10000))
    key = _run(_insert_token("t_token_fail", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 10000.0  # 10000 >= 10000 → 超限
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
    body = resp.json().get("error", "")
    assert "token_limit" in body.lower(), f"error should mention token_limit, got: {body}"


def test_token_limit_exceeded_type2_has_quota_passes(client):
    """token_limit 超限，但用户 quota_usd=50.0 → Type 2 放行，非 429。"""
    username = "user_token_limit_type2_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_token_type2_pass"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="token_limit", value=10000))
    key = _run(_insert_token("t_token_type2_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 10000.0  # Type 1 超限
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"Type 2 has quota, should not be 429, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Task 4：quota_limit 类型测试
# ---------------------------------------------------------------------------


def test_quota_limit_not_exceeded_passes(client):
    """quota_limit 规则：窗口内金额未超限 → 放行（非 429）。"""
    username = "user_quota_limit_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_quota_limit_pass"))
    _run(_insert_rate_limit(group_id, window_sec=3600, limit_type="quota_limit", value=10.0))
    key = _run(_insert_token("t_quota_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 9.99  # 9.99 < 10.0 → 通过
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"should not be 429, got {resp.status_code}: {resp.text}"


def test_quota_limit_exceeded_returns_429(client):
    """quota_limit 规则：窗口内金额超限 → 429，error 包含 quota_limit。"""
    username = "user_quota_limit_fail"
    _run(_insert_user(username, quota_usd=0))
    group_id = _run(_insert_group("group_quota_limit_fail"))
    _run(_insert_rate_limit(group_id, window_sec=3600, limit_type="quota_limit", value=10.0))
    key = _run(_insert_token("t_quota_fail", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 10.0  # 10.0 >= 10.0 → 超限
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
    body = resp.json().get("error", "")
    assert "quota_limit" in body.lower(), f"error should mention quota_limit, got: {body}"


def test_quota_limit_exceeded_type2_has_quota_passes(client):
    """quota_limit 超限，但用户 quota_usd=50.0 → Type 2 放行，非 429。"""
    username = "user_quota_limit_type2_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_quota_type2_pass"))
    _run(_insert_rate_limit(group_id, window_sec=3600, limit_type="quota_limit", value=10.0))
    key = _run(_insert_token("t_quota_type2_pass", username=username, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_sum", new_callable=AsyncMock
    ) as mock_sum:
        mock_sum.return_value = 10.0  # Type 1 超限
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"Type 2 has quota, should not be 429, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Task 5：同组多规则组合测试
# ---------------------------------------------------------------------------


def test_multi_rule_both_pass(client):
    """同组有 request_limit + token_limit，两条规则均未超限 → 放行。"""
    username = "user_multi_pass"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_multi_pass"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=10))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="token_limit", value=10000))
    key = _run(_insert_token("t_multi_pass", username=username, group_id=group_id))

    with patch("services.rate_limit_service.get_window_count", new_callable=AsyncMock) as mc, \
         patch("services.rate_limit_service.get_window_sum", new_callable=AsyncMock) as ms:
        mc.return_value = 5       # 5 < 10
        ms.return_value = 5000.0  # 5000 < 10000
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"both rules pass, should not be 429, got {resp.status_code}"


def test_multi_rule_request_exceeded(client):
    """同组两条规则，request_limit 超限 → 429（即使 token_limit 未超）。"""
    username = "user_multi_req_fail"
    _run(_insert_user(username, quota_usd=0))
    group_id = _run(_insert_group("group_multi_req_fail"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=10))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="token_limit", value=10000))
    key = _run(_insert_token("t_multi_req_fail", username=username, group_id=group_id))

    with patch("services.rate_limit_service.get_window_count", new_callable=AsyncMock) as mc, \
         patch("services.rate_limit_service.get_window_sum", new_callable=AsyncMock) as ms:
        mc.return_value = 10      # 10 >= 10 → request 超限
        ms.return_value = 5000.0  # token 未超（但规则顺序不定，request 超限即拒绝）
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"


def test_multi_rule_disabled_rule_skipped(client):
    """value=0 的规则应被跳过（禁用），不触发 429。"""
    username = "user_disabled_rule"
    _run(_insert_user(username, quota_usd=50.0))
    group_id = _run(_insert_group("group_disabled_rule"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=0))  # 禁用
    key = _run(_insert_token("t_disabled_rule", username=username, group_id=group_id))

    # 不需要 mock，禁用规则直接跳过，不查 Redis
    with patch(
        "middleware.auth._get_redis",
        new_callable=AsyncMock,
        return_value=AsyncMock(),
    ):
        resp = _post_chat(client, key)

    assert resp.status_code != 429, f"disabled rule should not 429, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Task 6：Token 绑定边界测试
# ---------------------------------------------------------------------------


def test_token_with_group_no_username_type1_exceeded_returns_429(client):
    """token 有 group 但无 username：Type 1 超限 → Type 2 无 username → 429。"""
    group_id = _run(_insert_group("group_no_username"))
    _run(_insert_rate_limit(group_id, window_sec=60, limit_type="request_limit", value=1))
    key = _run(_insert_token("t_no_username", username=None, group_id=group_id))

    with patch(
        "services.rate_limit_service.get_window_count", new_callable=AsyncMock
    ) as mock_count:
        mock_count.return_value = 1  # Type 1 超限
        resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"


def test_token_no_group_no_username_returns_429(client):
    """token 无 group 无 username：直接 Type 2，无 username → 429。"""
    key = _run(_insert_token("t_orphan", username=None, group_id=None))

    resp = _post_chat(client, key)

    assert resp.status_code == 429, f"expected 429, got {resp.status_code}: {resp.text}"
    assert "quota" in resp.json().get("error", "").lower()
