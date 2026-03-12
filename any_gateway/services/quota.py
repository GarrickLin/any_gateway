"""
额度检查与用量更新服务。

- check_quota: 纯逻辑，判断 token 是否在额度内
- update_usage: 更新 Token.used_usd + 插入 UsageLog，fire-and-forget 调用
"""
from __future__ import annotations

from sqlalchemy import case, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from fastcrud import FastCRUD
from loguru import logger

from db.database import engine
from db.models import Token, UsageLog, User


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
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
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
                **({"id": request_id} if request_id is not None else {}),
                token_id=token_id,
                channel_id=channel_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens,
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


def check_request_limit(current_count: int, limit: float) -> bool:
    """
    检查滚动窗口内请求次数是否在限制内。
    limit <= 0 表示禁用，始终返回 True。
    """
    if limit <= 0:
        return True
    return current_count < limit


def check_token_limit(current_tokens: int, limit: float) -> bool:
    """
    检查滚动窗口内 token 数是否在限制内。
    limit <= 0 表示禁用，始终返回 True。
    """
    if limit <= 0:
        return True
    return current_tokens < limit


def check_rolling_cost_limit(current_cost: float, limit: float) -> bool:
    """
    检查滚动窗口内总金额是否在限制内。
    limit <= 0 表示禁用，始终返回 True。
    """
    if limit <= 0:
        return True
    return current_cost < limit


async def update_user_balance(username: str | None, cost_usd: float) -> None:
    """
    响应完成后，原子扣减 User.quota_usd 并累加 User.used_usd。

    - username=None 或 cost_usd<=0：直接返回，不操作 DB
    - quota_usd=None（无限额度）：只累加 used_usd，不扣减 quota_usd
    - quota_usd>0：扣减 quota_usd（不低于 0），累加 used_usd
    - quota_usd=0：只累加 used_usd（已无余额，但记录消费）

    fire-and-forget：内部捕获所有异常，不影响响应返回。
    """
    if username is None or cost_usd <= 0:
        return

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            # 1. 始终累加 used_usd
            stmt_used = (
                sa_update(User)
                .where(User.username == username)
                .values(used_usd=User.used_usd + cost_usd)
            )
            await session.execute(stmt_used)

            # 2. 仅当 quota_usd IS NOT NULL 时，原子扣减（不低于 0）
            stmt_quota = (
                sa_update(User)
                .where(
                    User.username == username,
                    User.quota_usd.is_not(None),
                )
                .values(
                    quota_usd=case(
                        (User.quota_usd > cost_usd, User.quota_usd - cost_usd),
                        else_=0,
                    )
                )
            )
            await session.execute(stmt_quota)

            await session.commit()
    except Exception:
        logger.exception(f"update_user_balance 失败 (username={username})")


def check_account_quota(quota_usd: float | None) -> bool:
    """
    检查用户账户是否有余额可用。
    - None：无限额度，放行
    - > 0：有余额，放行
    - <= 0：无余额，拒绝
    """
    if quota_usd is None:
        return True
    return quota_usd > 0
