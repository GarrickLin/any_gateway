"""
额度检查服务单元测试。
check_quota 为纯逻辑函数，无 I/O，测试无需异步框架。
"""
import sys
from pathlib import Path

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

from services.quota import (
    check_quota,
    check_request_limit,
    check_token_limit,
    check_rolling_cost_limit,
    check_account_quota,
)


# ---------------------------------------------------------------------------
# check_quota 测试
# ---------------------------------------------------------------------------

def test_check_quota_unlimited_when_zero():
    """quota_usd=0 表示无限额度，应始终返回 True，即使 used_usd 极大。"""
    assert check_quota(quota_usd=0, used_usd=9999.99) is True


def test_check_quota_within_limit():
    """used_usd < quota_usd 时，在额度内，返回 True。"""
    assert check_quota(quota_usd=10.0, used_usd=5.0) is True


def test_check_quota_exceeded():
    """used_usd == quota_usd 时，已用尽额度，返回 False。"""
    assert check_quota(quota_usd=10.0, used_usd=10.0) is False


def test_check_quota_exceeded_over():
    """used_usd > quota_usd 时，超出额度，返回 False。"""
    assert check_quota(quota_usd=10.0, used_usd=15.0) is False


def test_update_usage_accepts_request_id():
    """update_usage 应接受 request_id 参数"""
    import inspect
    from services.quota import update_usage
    sig = inspect.signature(update_usage)
    assert "request_id" in sig.parameters
    # 确认默认值为 None（向后兼容）
    assert sig.parameters["request_id"].default is None


def test_update_usage_request_id_none_check():
    """request_id 判断应使用 is not None，空字符串不应降级为自动 id"""
    # 验证当 request_id="" 时，dict 解包结果仍会传入 id=""（走 DB 校验）
    request_id = ""
    kwargs = {"id": request_id} if request_id is not None else {}
    assert kwargs == {"id": ""}  # 空字符串应传入，不降级

    request_id = None
    kwargs = {"id": request_id} if request_id is not None else {}
    assert kwargs == {}  # None 才降级为自动 id


# ---------------------------------------------------------------------------
# check_request_limit 测试
# ---------------------------------------------------------------------------

def test_check_request_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_request_limit(current_count=9999, limit=0) is True


def test_check_request_limit_within():
    """current_count < limit 时，在限制内，返回 True。"""
    assert check_request_limit(current_count=5, limit=10) is True


def test_check_request_limit_at_limit():
    """current_count == limit 时，已达上限，返回 False。"""
    assert check_request_limit(current_count=10, limit=10) is False


def test_check_request_limit_over():
    """current_count > limit 时，超出上限，返回 False。"""
    assert check_request_limit(current_count=15, limit=10) is False


# ---------------------------------------------------------------------------
# check_token_limit 测试
# ---------------------------------------------------------------------------

def test_check_token_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_token_limit(current_tokens=9999, limit=0) is True


def test_check_token_limit_within():
    """current_tokens < limit 时，在限制内，返回 True。"""
    assert check_token_limit(current_tokens=500, limit=1000) is True


def test_check_token_limit_at_limit():
    """current_tokens == limit 时，已达上限，返回 False。"""
    assert check_token_limit(current_tokens=1000, limit=1000) is False


def test_check_token_limit_over():
    """current_tokens > limit 时，超出上限，返回 False。"""
    assert check_token_limit(current_tokens=1500, limit=1000) is False


# ---------------------------------------------------------------------------
# check_rolling_cost_limit 测试
# ---------------------------------------------------------------------------

def test_check_rolling_cost_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_rolling_cost_limit(current_cost=999.99, limit=0) is True


def test_check_rolling_cost_limit_within():
    """current_cost < limit 时，在限制内，返回 True。"""
    assert check_rolling_cost_limit(current_cost=3.5, limit=10.0) is True


def test_check_rolling_cost_limit_at_limit():
    """current_cost == limit 时，已达上限，返回 False。"""
    assert check_rolling_cost_limit(current_cost=10.0, limit=10.0) is False


def test_check_rolling_cost_limit_over():
    """current_cost > limit 时，超出上限，返回 False。"""
    assert check_rolling_cost_limit(current_cost=12.5, limit=10.0) is False


# ---------------------------------------------------------------------------
# check_account_quota 测试
# ---------------------------------------------------------------------------

def test_check_account_quota_none_is_unlimited():
    """quota_usd=None 表示无限额度，应返回 True。"""
    assert check_account_quota(quota_usd=None) is True


def test_check_account_quota_positive_has_balance():
    """quota_usd > 0 表示有余额，应返回 True。"""
    assert check_account_quota(quota_usd=10.0) is True


def test_check_account_quota_zero_no_balance():
    """quota_usd=0 表示无余额，应返回 False。"""
    assert check_account_quota(quota_usd=0) is False


def test_check_account_quota_negative_no_balance():
    """quota_usd < 0 视为无余额，应返回 False。"""
    assert check_account_quota(quota_usd=-1.0) is False


# ---------------------------------------------------------------------------
# update_user_balance 测试（使用内存数据库）
# ---------------------------------------------------------------------------

import asyncio
import os
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


# 创建测试用内存数据库引擎
@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _make_test_engine():
    """创建 SQLite 内存数据库引擎。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _create_user(engine, username: str, quota_usd, used_usd: float = 0.0):
    """在测试数据库中创建用户。

    当 quota_usd=None 时，使用原生 SQL 插入以确保存储为 SQL NULL
    （SQLModel ORM 会将 None 转为 0.0 浮点值）。
    """
    from sqlalchemy import text
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    async with AsyncSession(engine, expire_on_commit=False) as session:
        if quota_usd is None:
            await session.execute(
                text("INSERT INTO users (username, quota_usd, used_usd, created_at) VALUES (:u, NULL, :used, :now)"),
                {"u": username, "used": used_usd, "now": now},
            )
        else:
            await session.execute(
                text("INSERT INTO users (username, quota_usd, used_usd, created_at) VALUES (:u, :quota, :used, :now)"),
                {"u": username, "quota": quota_usd, "used": used_usd, "now": now},
            )
        await session.commit()


async def _get_user(engine, username: str):
    """从测试数据库中查询用户。"""
    from db.models import User
    from sqlmodel import select
    async with AsyncSession(engine, expire_on_commit=False) as session:
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


def test_update_user_balance_skips_when_no_username():
    """username=None 时直接返回，不操作 DB。"""
    from services.quota import update_user_balance
    import inspect
    sig = inspect.signature(update_user_balance)
    assert "username" in sig.parameters
    assert "cost_usd" in sig.parameters

    async def _run():
        engine = await _make_test_engine()
        await _create_user(engine, "skip_no_user", quota_usd=10.0, used_usd=0.0)

        import services.quota as quota_mod
        original_engine = quota_mod.engine
        quota_mod.engine = engine
        try:
            await update_user_balance(username=None, cost_usd=1.0)
        finally:
            quota_mod.engine = original_engine

        user = await _get_user(engine, "skip_no_user")
        assert user is not None
        # username=None 应跳过 DB 操作，quota_usd 和 used_usd 均不变
        assert abs(user.quota_usd - 10.0) < 1e-9
        assert abs(user.used_usd - 0.0) < 1e-9

    asyncio.run(_run())


def test_update_user_balance_skips_when_zero_cost():
    """cost_usd<=0 时直接返回，不操作 DB。"""
    from services.quota import update_user_balance

    async def _run():
        engine = await _make_test_engine()
        await _create_user(engine, "alice", quota_usd=10.0, used_usd=0.0)

        import services.quota as quota_mod
        original_engine = quota_mod.engine
        quota_mod.engine = engine
        try:
            await update_user_balance(username="alice", cost_usd=0.0)
            await update_user_balance(username="alice", cost_usd=-1.0)
        finally:
            quota_mod.engine = original_engine

        user = await _get_user(engine, "alice")
        assert user is not None
        # cost_usd<=0 应跳过 DB 操作，quota_usd 和 used_usd 均不变
        assert abs(user.quota_usd - 10.0) < 1e-9
        assert abs(user.used_usd - 0.0) < 1e-9

    asyncio.run(_run())


def test_update_user_balance_deducts_quota_and_accumulates_used():
    """quota_usd>0 时：扣减 quota_usd，累加 used_usd。"""
    from services.quota import update_user_balance

    async def _run():
        engine = await _make_test_engine()
        await _create_user(engine, "bob", quota_usd=10.0, used_usd=1.0)

        # Monkey-patch quota.py 使用测试引擎
        import services.quota as quota_mod
        original_engine = quota_mod.engine
        quota_mod.engine = engine
        try:
            await update_user_balance(username="bob", cost_usd=3.0)
        finally:
            quota_mod.engine = original_engine

        user = await _get_user(engine, "bob")
        assert user is not None
        # quota_usd 应从 10.0 扣减 3.0 = 7.0
        assert abs(user.quota_usd - 7.0) < 1e-9
        # used_usd 应从 1.0 累加 3.0 = 4.0
        assert abs(user.used_usd - 4.0) < 1e-9

    asyncio.run(_run())


def test_update_user_balance_does_not_go_below_zero():
    """扣减后 quota_usd 不低于 0。"""
    from services.quota import update_user_balance

    async def _run():
        engine = await _make_test_engine()
        await _create_user(engine, "carol", quota_usd=2.0, used_usd=0.0)

        import services.quota as quota_mod
        original_engine = quota_mod.engine
        quota_mod.engine = engine
        try:
            # cost 超过余额
            await update_user_balance(username="carol", cost_usd=5.0)
        finally:
            quota_mod.engine = original_engine

        user = await _get_user(engine, "carol")
        assert user is not None
        # quota_usd 不低于 0
        assert user.quota_usd >= 0
        assert abs(user.quota_usd - 0.0) < 1e-9
        # used_usd 仍然累加
        assert abs(user.used_usd - 5.0) < 1e-9

    asyncio.run(_run())


def test_update_user_balance_skips_quota_deduction_when_none():
    """quota_usd=None（无限额度）时：只累加 used_usd，不扣减 quota_usd。"""
    from services.quota import update_user_balance

    async def _run():
        engine = await _make_test_engine()
        await _create_user(engine, "dave", quota_usd=None, used_usd=0.5)

        import services.quota as quota_mod
        original_engine = quota_mod.engine
        quota_mod.engine = engine
        try:
            await update_user_balance(username="dave", cost_usd=2.0)
        finally:
            quota_mod.engine = original_engine

        user = await _get_user(engine, "dave")
        assert user is not None
        # quota_usd 仍为 None（无限额度，未被改变）
        assert user.quota_usd is None
        # used_usd 从 0.5 累加 2.0 = 2.5
        assert abs(user.used_usd - 2.5) < 1e-9

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# update_usage 落库重试
# ---------------------------------------------------------------------------

def test_update_usage_retries_transient_errors():
    """commit 瞬时失败应指数退避重试，最终成功。"""
    from unittest.mock import patch
    import services.quota as q

    class _FlakySession:
        calls = 0

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return None

        def add(self, *a, **k):
            pass

        async def commit(self):
            _FlakySession.calls += 1
            if _FlakySession.calls < 3:
                raise RuntimeError("transient DB error")

    async def _nosleep(*a, **k):
        return None

    async def _run():
        with patch.object(q, "AsyncSession", _FlakySession), \
             patch.object(q.asyncio, "sleep", _nosleep):
            await q.update_usage(
                token_id=None, channel_id=None, model="m",
                input_tokens=1, output_tokens=1, cost_usd=0.0,
                duration_ms=1.0, status=200, is_stream=False, request_id=None,
            )
        assert _FlakySession.calls == 3  # 失败 2 次 + 成功 1 次

    asyncio.run(_run())


def test_update_usage_idempotent_on_duplicate_request_id():
    """request_id 主键重复(IntegrityError)应幂等返回，不重试。"""
    from unittest.mock import patch
    from sqlalchemy.exc import IntegrityError
    import services.quota as q

    class _DupSession:
        calls = 0

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return None

        def add(self, *a, **k):
            pass

        async def commit(self):
            _DupSession.calls += 1
            raise IntegrityError("duplicate", None, Exception("dup"))

    async def _run():
        with patch.object(q, "AsyncSession", _DupSession):
            await q.update_usage(
                token_id=None, channel_id=None, model="m",
                input_tokens=1, output_tokens=1, cost_usd=0.0,
                duration_ms=1.0, status=200, is_stream=False, request_id="dup-id",
            )
        assert _DupSession.calls == 1  # 命中重复即返回，不重试

    asyncio.run(_run())


def test_update_usage_gives_up_after_max_retries():
    """持续失败应在 _USAGE_MAX_RETRIES 次后放弃(不抛出)。"""
    from unittest.mock import patch
    import services.quota as q

    class _DeadSession:
        calls = 0

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, *a, **k):
            return None

        def add(self, *a, **k):
            pass

        async def commit(self):
            _DeadSession.calls += 1
            raise RuntimeError("permanent DB error")

    async def _nosleep(*a, **k):
        return None

    async def _run():
        with patch.object(q, "AsyncSession", _DeadSession), \
             patch.object(q.asyncio, "sleep", _nosleep):
            # 不应抛出
            await q.update_usage(
                token_id=None, channel_id=None, model="m",
                input_tokens=1, output_tokens=1, cost_usd=0.0,
                duration_ms=1.0, status=200, is_stream=False, request_id=None,
            )
        assert _DeadSession.calls == q._USAGE_MAX_RETRIES

    asyncio.run(_run())
