"""测试懒加载用户创建逻辑。"""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    async def _run():
        # 导入模型确保 metadata 注册
        import db.models  # noqa: F401
        async with ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        # 插入 default 分组
        from db.models import UserGroup
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            s.add(UserGroup(name="default"))
            await s.commit()
    asyncio.run(_run())
    yield
    asyncio.run(ENGINE.dispose())


def test_lazy_create_user_new():
    """首次调用应创建 User 记录，不写入 UserGroupMembership。"""
    from services.auth_service import lazy_create_user
    from db.models import User, UserGroupMembership

    async def _run():
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            await lazy_create_user("alice", s)
            await s.commit()
            user = await s.get(User, "alice")
            result = await s.execute(
                select(UserGroupMembership).where(UserGroupMembership.username == "alice")
            )
            memberships = result.scalars().all()
        return user, memberships

    user, memberships = asyncio.run(_run())
    assert user is not None
    assert user.username == "alice"
    assert len(memberships) == 0  # 不再写入 membership，分组可见性由 all_visible 动态控制


def test_lazy_create_user_idempotent():
    """重复调用不应报错，User 记录仍唯一，不写入 membership。"""
    from services.auth_service import lazy_create_user
    from db.models import User, UserGroupMembership

    async def _run():
        async with AsyncSession(ENGINE, expire_on_commit=False) as s:
            await lazy_create_user("alice", s)  # 第二次调用（alice 已存在）
            await s.commit()
            user = await s.get(User, "alice")
            result = await s.execute(
                select(UserGroupMembership).where(UserGroupMembership.username == "alice")
            )
            return user, result.scalars().all()

    user, memberships = asyncio.run(_run())
    assert user is not None
    assert len(memberships) == 0  # 依然没有 membership 记录


def test_lazy_create_user_no_default_group():
    """当 default 分组不存在时，应仅创建 User，不报错。"""
    from services.auth_service import lazy_create_user
    from db.models import User

    async def _run():
        # 使用全新的独立引擎（无 default 分组）
        fresh_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        import db.models  # noqa: F401
        async with fresh_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        # 没有插入 default 分组
        async with AsyncSession(fresh_engine, expire_on_commit=False) as s:
            await lazy_create_user("bob", s)  # 应不报错
            await s.commit()
            user = await s.get(User, "bob")
        return user

    user = asyncio.run(_run())
    assert user is not None
    assert user.username == "bob"
