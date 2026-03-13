"""计价功能测试"""
import os
import sys
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import SQLModel

_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

os.environ.setdefault("ADMIN_KEY", "test-admin-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_FALLBACK_KEY", "fallback-key")

TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    async def _create():
        import db.models  # noqa
        async with TEST_ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    asyncio.run(_create())


@pytest.fixture
def client():
    import db.database as _db
    import gateway as _gw
    import middleware.auth as _auth_mw
    import services.quota as _quota
    from db.database import async_session_generator

    async def override_session():
        async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
            yield session

    orig_db = _db.engine
    orig_gw = _gw.engine
    orig_mw = getattr(_auth_mw, "engine", None)
    orig_quota = getattr(_quota, "engine", None)

    _db.engine = TEST_ENGINE
    _gw.engine = TEST_ENGINE
    _auth_mw.engine = TEST_ENGINE
    _quota.engine = TEST_ENGINE

    from gateway import app
    app.dependency_overrides[async_session_generator] = override_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()

    _db.engine = orig_db
    _gw.engine = orig_gw
    if orig_mw is not None:
        _auth_mw.engine = orig_mw
    if orig_quota is not None:
        _quota.engine = orig_quota


# ── Task 1 tests ──────────────────────────────────────────────────────────────

def test_model_price_importable():
    from db.models import ModelPrice, ModelPriceCreate, ModelPriceUpdate
    p = ModelPrice(model_name="gpt-4", unit="input_token", price_per_unit=10.0)
    assert p.unit == "input_token"
    assert p.price_per_unit == 10.0


def test_group_model_price_importable():
    from db.models import GroupModelPrice
    gp = GroupModelPrice(group_id="g1", model_name="gpt-4", unit="output_token", price_per_unit=30.0)
    assert gp.group_id == "g1"


def test_usage_log_has_covered_by_package():
    from db.models import UsageLog
    log = UsageLog()
    assert log.covered_by_package is False


def test_voucher_code_auto_generated():
    from db.models import Voucher
    v = Voucher(amount_usd=10.0)
    assert v.code is not None and len(v.code) > 0


# ── Task 2 tests ──────────────────────────────────────────────────────────────

def test_match_exact():
    from services.pricing import match_model_name
    assert match_model_name("gpt-4", "gpt-4") is True


def test_match_fuzzy_spaces():
    from services.pricing import match_model_name
    assert match_model_name("chatgpt-turbo-3.5", "gpt 3.5 turbo") is True


def test_match_no_match():
    from services.pricing import match_model_name
    assert match_model_name("claude-3-opus", "gpt 3.5 turbo") is False


def test_calculate_cost_zero_no_price():
    """没有价格表时 cost = 0"""
    from services.pricing import calculate_cost

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        async with engine.begin() as conn:
            import db.models  # noqa
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as session:
            return await calculate_cost(session, None, "gpt-4", 1000, 500)

    assert asyncio.run(run()) == 0.0


def test_calculate_cost_global_price():
    """全局价格表计算：1M input @ $10 + 1M output @ $30 = $40"""
    from services.pricing import calculate_cost
    from db.models import ModelPrice

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        async with engine.begin() as conn:
            import db.models  # noqa
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add(ModelPrice(model_name="gpt-4", unit="input_token", price_per_unit=10.0))
            session.add(ModelPrice(model_name="gpt-4", unit="output_token", price_per_unit=30.0))
            await session.commit()
            return await calculate_cost(session, None, "gpt-4", 1_000_000, 1_000_000)

    result = asyncio.run(run())
    assert abs(result - 40.0) < 1e-9


def test_calculate_cost_group_price_overrides_global():
    """Group 价格优先于全局价格"""
    from services.pricing import calculate_cost
    from db.models import ModelPrice, GroupModelPrice, UserGroup

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        async with engine.begin() as conn:
            import db.models  # noqa
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            group = UserGroup(name="vip")
            session.add(group)
            await session.commit()
            await session.refresh(group)
            group_id = group.id
            session.add(ModelPrice(model_name="gpt-4", unit="input_token", price_per_unit=10.0))
            session.add(GroupModelPrice(group_id=group_id, model_name="gpt-4", unit="input_token", price_per_unit=5.0))
            await session.commit()
            return await calculate_cost(session, group_id, "gpt-4", 1_000_000, 0)

    result = asyncio.run(run())
    assert abs(result - 5.0) < 1e-9


def test_calculate_cost_request_unit():
    """request 单位：固定每次费用"""
    from services.pricing import calculate_cost
    from db.models import ModelPrice

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        async with engine.begin() as conn:
            import db.models  # noqa
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add(ModelPrice(model_name="nano", unit="request", price_per_unit=0.006))
            await session.commit()
            return await calculate_cost(session, None, "nano", 1000, 500)

    result = asyncio.run(run())
    assert abs(result - 0.006) < 1e-9
