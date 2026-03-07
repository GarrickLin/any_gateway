"""测试新增模型的表结构和默认值。"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

# 提前导入所有模型，确保注册到 SQLModel.metadata
import db.models  # noqa: F401, E402

ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="module", autouse=True)
def setup():
    SQLModel.metadata.create_all(ENGINE)


def test_user_model_importable():
    from db.models import User
    assert User.__tablename__ == "users"


def test_user_group_membership_importable():
    from db.models import UserGroupMembership
    assert UserGroupMembership.__tablename__ == "user_group_memberships"


def test_group_channel_importable():
    from db.models import GroupChannel
    assert GroupChannel.__tablename__ == "group_channels"


def test_usergroup_tpm_limit_default():
    from db.models import UserGroup
    g = UserGroup(name="test")
    assert g.tpm_limit == 1_000_000
    assert g.rpm_limit == 60
    assert g.priority == 1
    assert g.multiplier == 1.0


def test_token_has_username_field():
    from db.models import Token
    t = Token(name="test")
    assert hasattr(t, "username")
    assert t.username is None


def test_user_primary_key_uniqueness():
    """User.username 主键重复插入应报 IntegrityError。"""
    from db.models import User

    with Session(ENGINE) as s:
        s.add(User(username="dup-user"))
        s.commit()

    # 第二次插入同一 username 应失败
    with Session(ENGINE) as s:
        s.add(User(username="dup-user"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_user_group_membership_unique_constraint():
    """UserGroupMembership 联合主键重复插入应报 IntegrityError。"""
    from db.models import User, UserGroup, UserGroupMembership

    with Session(ENGINE) as s:
        grp = UserGroup(name="ug-test-grp")
        usr = User(username="ug-test-user")
        s.add_all([grp, usr])
        s.flush()
        s.add(UserGroupMembership(username="ug-test-user", group_id=grp.id))
        s.commit()
        gid = grp.id

    # 重复插入同一 (username, group_id) 应失败
    with Session(ENGINE) as s:
        s.add(UserGroupMembership(username="ug-test-user", group_id=gid))
        with pytest.raises(IntegrityError):
            s.commit()


def test_init_db_creates_default_group():
    """init_db 应在启动时幂等地创建 default 分组。"""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, select
    import db.database as _db
    from db.models import UserGroup

    ASYNC_ENGINE = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run():
        # 先建表
        async with ASYNC_ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # 替换 engine，调用 init_db
        _orig = _db.engine
        try:
            _db.engine = ASYNC_ENGINE
            await _db.init_db()
            # 幂等：第二次调用不应报错
            await _db.init_db()
        finally:
            _db.engine = _orig

        # 查询 default 分组
        async with AsyncSession(ASYNC_ENGINE, expire_on_commit=False) as s:
            result = await s.execute(select(UserGroup).where(UserGroup.name == "default"))
            return result.scalar_one_or_none()

    grp = asyncio.run(_run())
    assert grp is not None
    assert grp.name == "default"
    assert grp.rpm_limit == 60
    assert grp.tpm_limit == 1_000_000
    assert grp.priority == 1
    assert grp.multiplier == 1.0
