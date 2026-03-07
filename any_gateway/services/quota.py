"""
额度检查与用量更新服务。

- check_quota: 纯逻辑，判断 token 是否在额度内
- update_usage: 更新 Token.used_usd + 插入 UsageLog，fire-and-forget 调用
"""
from __future__ import annotations

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from fastcrud import FastCRUD
from loguru import logger

from db.database import engine
from db.models import Token, UsageLog


def check_quota(quota_usd: float, used_usd: float) -> bool:
    """
    判断 token 是否在额度内。
    quota_usd <= 0 表示无限额度，始终返回 True。
    否则返回 used_usd < quota_usd。

    注意：此函数为纯逻辑，无 I/O，设计为同步函数。
    """
    if quota_usd <= 0:
        return True
    return used_usd < quota_usd


async def update_usage(
    token_id: str | None,
    channel_id: str | None,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: float,
    status: int | None,
    is_stream: bool,
    username: str | None = None,
    request_id: str | None = None,  # 新增：外部传入时作为 UsageLog.id
) -> None:
    """
    1. 递增 Token.used_usd（通过 SQL 级原子 UPDATE）
    2. 插入一条 UsageLog 记录

    此函数应通过 asyncio.create_task() 以 fire-and-forget 方式调用，
    内部捕获所有异常，确保用量更新失败不会影响正常请求。

    TODO: 实现真实的价格计算（目前 cost_usd 始终为 0）
    """
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            # 1. 原子递增 Token.used_usd（SQL 级 UPDATE，避免 read-modify-write 竞态）
            if token_id:
                stmt = sa_update(Token).where(Token.id == token_id).values(
                    used_usd=Token.used_usd + cost_usd
                )
                await session.execute(stmt)

            # 2. 插入 UsageLog 记录
            log = UsageLog(
                **({"id": request_id} if request_id else {}),
                token_id=token_id,
                channel_id=channel_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                status=status,
                is_stream=is_stream,
                username=username,
            )
            session.add(log)
            await session.commit()

    except Exception as exc:  # pylint: disable=broad-except
        # 用量记录失败不应影响请求结果，仅记录错误日志
        logger.exception(f"update_usage 失败 (token_id={token_id})")
