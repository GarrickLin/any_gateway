"""
定价服务：模型名模糊匹配、价格查询（Group 优先 Global 兜底）、费用计算。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GroupModelPrice, ModelPrice


def match_model_name(real_model_name: str, table_model_name: str) -> bool:
    """判断 table_model_name 是否匹配 real_model_name。

    含空格则拆词后 AND 匹配（模糊），否则精确匹配（忽略大小写）。
    """
    real = real_model_name.strip().lower()
    words = table_model_name.strip().lower().split()
    if not words:
        return False
    return all(w in real for w in words)


async def _lookup_price(
    session: AsyncSession,
    group_id: str | None,
    model: str,
    unit: str,
) -> float:
    """查询指定 unit 的单价。Group 自定义价格优先，全局兜底，找不到返回 0.0。"""
    if group_id:
        result = await session.execute(
            select(GroupModelPrice).where(
                GroupModelPrice.group_id == group_id,
                GroupModelPrice.unit == unit,
            )
        )
        for row in result.scalars().all():
            if match_model_name(model, row.model_name):
                return row.price_per_unit

    result = await session.execute(
        select(ModelPrice).where(ModelPrice.unit == unit)
    )
    for row in result.scalars().all():
        if match_model_name(model, row.model_name):
            return row.price_per_unit

    return 0.0


async def calculate_cost(
    session: AsyncSession,
    group_id: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    multiplier: float = 1.0,
) -> float:
    """计算本次请求费用（USD）。

    优先检查 request 定价（固定费），否则按 token 公式计算。
    multiplier 传入 group.multiplier（默认 1.0）。
    """
    M = 1_000_000

    req_price = await _lookup_price(session, group_id, model, "request")
    if req_price > 0:
        return round(req_price * multiplier, 8)

    input_price = await _lookup_price(session, group_id, model, "input_token")
    output_price = await _lookup_price(session, group_id, model, "output_token")
    cache_read_price = await _lookup_price(session, group_id, model, "cache_read_token")
    cache_write_price = await _lookup_price(session, group_id, model, "cache_write_token")

    cost = (
        (input_tokens / M * input_price)
        + (output_tokens / M * output_price)
        + (cache_read_tokens / M * cache_read_price)
        + (cache_creation_tokens / M * cache_write_price)
    )
    return round(cost * multiplier, 8)
