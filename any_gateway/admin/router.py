"""
Admin CRUD API 路由。

- 使用 FastCRUD crud_router 自动生成 Token/Channel/UserGroup 的 CRUD 接口。
- 手动编写业务路由：冻结 Token、统计概览、Token 用量 Top10、模型请求 Top10。
- 所有 /admin/* 路由均需要 x-admin-key Header 校验。
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastcrud import FastCRUD, crud_router
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import async_session_generator
from db.models import (
    Channel,
    ChannelCreate,
    ChannelUpdate,
    Token,
    TokenCreate,
    TokenUpdate,
    UsageLog,
    UserGroup,
    UserGroupCreate,
    UserGroupUpdate,
)

# ---------------------------------------------------------------------------
# Admin Key 验证依赖
# ---------------------------------------------------------------------------

ADMIN_KEY: str = os.environ.get("ADMIN_KEY", "")


async def verify_admin_key(x_admin_key: str = Header(...)) -> None:
    """校验 x-admin-key header，不匹配则返回 403。"""
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        logger.warning("Admin key 校验失败")
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ---------------------------------------------------------------------------
# FastCRUD 自动生成的 CRUD 路由
# fastcrud 的 *_deps 参数接受可调用对象（函数），不是 Depends() 包装对象。
# ---------------------------------------------------------------------------

_common_deps = [verify_admin_key]

token_router: APIRouter = crud_router(
    session=async_session_generator,
    model=Token,
    create_schema=TokenCreate,
    update_schema=TokenUpdate,
    path="/admin/tokens",
    tags=["Admin: Tokens"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

channel_router: APIRouter = crud_router(
    session=async_session_generator,
    model=Channel,
    create_schema=ChannelCreate,
    update_schema=ChannelUpdate,
    path="/admin/channels",
    tags=["Admin: Channels"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

group_router: APIRouter = crud_router(
    session=async_session_generator,
    model=UserGroup,
    create_schema=UserGroupCreate,
    update_schema=UserGroupUpdate,
    path="/admin/groups",
    tags=["Admin: Groups"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

# ---------------------------------------------------------------------------
# 手动业务路由
# ---------------------------------------------------------------------------

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)],
)


# ------ 冻结 / 解冻 Token --------------------------------------------------

class FreezeBody:
    """请求体解析辅助（避免引入额外 Pydantic 模型）。"""

    def __init__(self, frozen: bool):
        self.frozen = frozen


from pydantic import BaseModel


class FreezeRequest(BaseModel):
    frozen: bool


@admin_router.patch("/tokens/{token_id}/freeze", summary="冻结 / 解冻 Token")
async def freeze_token(
    token_id: str,
    body: FreezeRequest,
    session: AsyncSession = Depends(async_session_generator),
) -> dict[str, Any]:
    """将指定 Token 设置为冻结（frozen=True）或解冻（frozen=False）。"""
    crud = FastCRUD(Token)
    token = await crud.get(session, id=token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    await crud.update(session, object={"frozen": body.frozen}, id=token_id)
    # 重新查询以返回最新状态
    updated = await crud.get(session, id=token_id)
    logger.info(f"Token {token_id} frozen={body.frozen}")
    return updated  # type: ignore[return-value]


# ------ 统计接口 ------------------------------------------------------------

def _today_prefix() -> str:
    """返回今日日期前缀（ISO 8601，用于 LIKE 查询）。"""
    from datetime import date

    return date.today().isoformat()  # e.g. "2026-03-04"


@admin_router.get("/stats/overview", summary="今日整体统计")
async def stats_overview(
    session: AsyncSession = Depends(async_session_generator),
) -> dict[str, Any]:
    """返回今日总费用（USD）和请求数。"""
    today = _today_prefix()
    stmt = select(
        func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        func.count(UsageLog.id).label("request_count"),
    ).where(UsageLog.created_at.like(f"{today}%"))

    result = await session.execute(stmt)
    row = result.one()
    return {
        "total_cost_usd": float(row.total_cost_usd),
        "request_count": int(row.request_count),
        "date": today,
    }


@admin_router.get("/stats/tokens", summary="Top 10 Token 用量")
async def stats_tokens(
    session: AsyncSession = Depends(async_session_generator),
) -> list[dict[str, Any]]:
    """返回今日费用 Top 10 的 Token（按 cost_usd 降序）。"""
    today = _today_prefix()
    stmt = (
        select(
            UsageLog.token_id,
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
            func.count(UsageLog.id).label("request_count"),
        )
        .where(UsageLog.created_at.like(f"{today}%"))
        .group_by(UsageLog.token_id)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "token_id": row.token_id,
            "total_cost_usd": float(row.total_cost_usd),
            "request_count": int(row.request_count),
        }
        for row in rows
    ]


@admin_router.get("/stats/models", summary="Top 10 模型请求量")
async def stats_models(
    session: AsyncSession = Depends(async_session_generator),
) -> list[dict[str, Any]]:
    """返回今日请求数 Top 10 的模型（按 request_count 降序）。"""
    today = _today_prefix()
    stmt = (
        select(
            UsageLog.model,
            func.count(UsageLog.id).label("request_count"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        )
        .where(UsageLog.created_at.like(f"{today}%"))
        .group_by(UsageLog.model)
        .order_by(func.count(UsageLog.id).desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "model": row.model,
            "request_count": int(row.request_count),
            "total_cost_usd": float(row.total_cost_usd),
        }
        for row in rows
    ]
