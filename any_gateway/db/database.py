import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/gateway.db")
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def async_session_generator() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


async def init_db():
    """在 FastAPI lifespan 启动时调用，自动建表（如表已存在则跳过）"""
    # 确保数据目录存在（仅对 sqlite:/// 路径有意义）
    if "sqlite" in DATABASE_URL:
        db_path = DATABASE_URL.split("///")[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
