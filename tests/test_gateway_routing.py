"""测试基于用户分组的网关路由逻辑。"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

os.environ.setdefault("ADMIN_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="module", autouse=True)
def setup():
    import db.database as _db
    original_engine = _db.engine  # 保存原始 engine

    async def _run():
        import db.models  # noqa: F401 - 确保所有表注册到 metadata
        async with ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        from db.models import UserGroup, Channel, User, UserGroupMembership, GroupChannel
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            # 两个分组，优先级不同
            g_high = UserGroup(name="premium", priority=10)
            g_low = UserGroup(name="standard", priority=1)
            s.add_all([g_high, g_low])
            await s.flush()

            # 两个渠道，分属不同分组
            c1 = Channel(name="premium-ch", provider="openai",
                         base_url="http://premium/v1", api_key="key1",
                         weight=1, enabled=True,
                         models=json.dumps(["gpt-4o"]))
            c2 = Channel(name="standard-ch", provider="openai",
                         base_url="http://standard/v1", api_key="key2",
                         weight=1, enabled=True,
                         models=json.dumps(["gpt-4o", "gpt-3.5-turbo"]))
            s.add_all([c1, c2])
            await s.flush()

            # 分组-渠道关联
            s.add(GroupChannel(group_id=g_high.id, channel_id=c1.id))
            s.add(GroupChannel(group_id=g_low.id, channel_id=c2.id))

            # 用户 alice 同时在两个分组
            u = User(username="alice")
            s.add(u)
            s.add(UserGroupMembership(username="alice", group_id=g_high.id))
            s.add(UserGroupMembership(username="alice", group_id=g_low.id))
            await s.commit()

    # 覆盖 gateway 使用的 engine，在 yield 之前替换
    _db.engine = ENGINE

    # gateway.py 使用 `from db.database import engine`，需要同时覆盖其本地绑定
    import gateway as _gw
    original_gw_engine = _gw.engine
    _gw.engine = ENGINE

    asyncio.run(_run())
    yield  # 测试运行
    _db.engine = original_engine  # teardown: 还原 db.database.engine
    _gw.engine = original_gw_engine  # teardown: 还原 gateway.engine


def test_routing_picks_highest_priority_group():
    """有 username 时应路由到优先级最高的分组的渠道。"""
    from gateway import find_backend_for_model

    result = asyncio.run(find_backend_for_model("gpt-4o", username="alice"))
    assert result is not None
    assert result["base_url"] == "http://premium/v1"


def test_routing_fallback_to_lower_group_when_model_not_in_high():
    """高优先级分组无此模型时，回落到低优先级分组。"""
    from gateway import find_backend_for_model

    result = asyncio.run(find_backend_for_model("gpt-3.5-turbo", username="alice"))
    assert result is not None
    assert result["base_url"] == "http://standard/v1"


def test_routing_without_username_fallback():
    """无 username 且无 group_id 时应拒绝访问（返回 None）。"""
    from gateway import find_backend_for_model

    result = asyncio.run(find_backend_for_model("gpt-4o", username=None))
    assert result is None  # 匿名 token 不允许访问


def test_routing_unknown_model_returns_none():
    """未知模型应返回 None。"""
    from gateway import find_backend_for_model

    result = asyncio.run(find_backend_for_model("nonexistent-model", username="alice"))
    assert result is None


def test_routing_by_token_group_id():
    """token 有 group_id 时，应直接按绑定分组路由，忽略用户组关系。"""
    from gateway import find_backend_for_model
    from db.models import UserGroup
    from sqlalchemy.ext.asyncio import AsyncSession

    # 获取 standard 分组的 id
    async def _get_standard_id():
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            from sqlmodel import select
            res = await s.execute(select(UserGroup).where(UserGroup.name == "standard"))
            grp = res.scalar_one()
            return grp.id

    std_id = asyncio.run(_get_standard_id())

    # alice 本来应路由到 premium（优先级高），但绑定 standard group 后应路由到 standard
    result = asyncio.run(find_backend_for_model("gpt-4o", username="alice", group_id=std_id))
    assert result is not None
    assert result["base_url"] == "http://standard/v1"


def test_routing_anonymous_with_group_id():
    """无 username 但有 group_id 时，应能路由成功。"""
    from gateway import find_backend_for_model
    from db.models import UserGroup
    from sqlalchemy.ext.asyncio import AsyncSession

    async def _get_premium_id():
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            from sqlmodel import select
            res = await s.execute(select(UserGroup).where(UserGroup.name == "premium"))
            grp = res.scalar_one()
            return grp.id

    prem_id = asyncio.run(_get_premium_id())

    result = asyncio.run(find_backend_for_model("gpt-4o", username=None, group_id=prem_id))
    assert result is not None
    assert result["base_url"] == "http://premium/v1"
