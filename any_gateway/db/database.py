import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy import text
from sqlmodel import SQLModel, select

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/gateway.db")

if "sqlite" in DATABASE_URL:
    _db_path = DATABASE_URL.split("///")[-1]
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine_kwargs = {
    "echo": False,
    "connect_args": {"check_same_thread": False},
}

# StaticPool 适合内存 SQLite；文件型 SQLite 复用单一异步连接时，
# 请求取消后容易把后续请求共用的连接一并终止。
if DATABASE_URL.endswith(":memory:"):
    engine_kwargs["poolclass"] = StaticPool

engine = create_async_engine(DATABASE_URL, **engine_kwargs)


async def async_session_generator() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def init_db():
    """在 FastAPI lifespan 启动时调用，自动建表（如表已存在则跳过）"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with engine.begin() as conn:
        for col_name, col_type in [
            ("context_length", "INTEGER"),
            ("vendor", "TEXT"),
            ("stability", "TEXT"),
        ]:
            try:
                await conn.execute(text(
                    f"ALTER TABLE model_prices ADD COLUMN {col_name} {col_type}"
                ))
            except Exception:
                pass

    # channels 表的渠道级网络/兼容性选项（幂等自动加列，免手动迁移）。
    # 每列单独事务：避免某条因列已存在而失败时，在 PostgreSQL 上污染同一事务。
    _bool_col = (
        "BOOLEAN NOT NULL DEFAULT false"
        if engine.dialect.name == "postgresql"
        else "BOOLEAN NOT NULL DEFAULT 0"
    )
    for col_name, col_type in [
        ("proxy_url", "VARCHAR"),
        ("disable_ssl", _bool_col),
        ("disable_compression", _bool_col),
    ]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    f"ALTER TABLE channels ADD COLUMN {col_name} {col_type}"
                ))
        except Exception:
            pass

    # 确保 default 分组存在（幂等）
    from db.models import UserGroup
    async with AsyncSession(engine, expire_on_commit=False) as session:
        result = await session.execute(
            select(UserGroup).where(UserGroup.name == "default")
        )
        if result.scalar_one_or_none() is None:
            session.add(UserGroup(name="default"))
            await session.commit()
