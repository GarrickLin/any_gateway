"""
限流决策服务（与中间件解耦）。
check_rate_limits：给定 group_id + redis_client + db session，检查所有 Type 1 规则。
返回 (passed: bool, error_msg: str | None)
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from fastcrud import FastCRUD
from loguru import logger

from db.models import RateLimit
from services.rate_limit_redis import build_key, get_window_count, get_window_sum
from services.quota import check_request_limit, check_token_limit, check_rolling_cost_limit


async def check_rate_limits(
    group_id: str,
    redis_client,
    session: AsyncSession,
    username: str | None = None,
) -> tuple[bool, str | None]:
    """
    检查 group 的所有 RateLimit 规则。
    username 存在时使用 per-user key，否则使用 group 级 key（共用同一套规则）。
    返回 (True, None) 表示全部通过，(False, "error msg") 表示超限。
    value=0 的规则跳过（禁用）。
    Redis 不可用时 fail open（get_window_* 已内部处理）。
    """
    crud = FastCRUD(RateLimit)
    result = await crud.get_multi(session, group_id=group_id)
    rules = result.get("data", [])
    enabled_rules = [rule for rule in rules if rule["value"] > 0]

    # 空规则集不应被视为套餐覆盖，否则仅因 token 绑定了 group 就会跳过余额扣费。
    if not enabled_rules:
        return False, "no active package rules configured"

    for rule in enabled_rules:
        limit_type = rule["limit_type"]
        window_sec = rule["window_sec"]
        value = rule["value"]

        key = build_key(group_id, limit_type, window_sec, username)

        if limit_type == "request_limit":
            current = await get_window_count(redis_client, key, window_sec)
            if not check_request_limit(current, value):
                return False, f"request_limit exceeded: {int(current)}/{int(value)} requests in {window_sec}s"

        elif limit_type == "token_limit":
            current = await get_window_sum(redis_client, key, window_sec)
            if not check_token_limit(int(current), value):
                return False, f"token_limit exceeded: {int(current)}/{int(value)} tokens in {window_sec}s"

        elif limit_type == "quota_limit":
            current = await get_window_sum(redis_client, key, window_sec)
            if not check_rolling_cost_limit(current, value):
                return False, f"quota_limit exceeded: {current:.2f}/{value:.2f} USD in {window_sec}s"

    return True, None
