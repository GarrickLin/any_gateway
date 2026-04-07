"""
Redis ZSET 精确滑动窗口限流服务。

Key 格式：rate:{group_id}:{limit_type}:{window_sec}
计数型（request_limit）：ZADD score=timestamp, member=request_id
求和型（token_limit/quota_limit）：ZADD score=timestamp, member="{req_id}:{value}"

所有操作通过 Lua 脚本原子执行，Redis 不可用时 fail open（返回 0，不抛异常）。
"""
from __future__ import annotations

import time
from loguru import logger


# ---------------------------------------------------------------------------
# Lua 脚本
# ---------------------------------------------------------------------------

# 读取当前窗口计数（清理过期 + ZCARD）
_LUA_GET_COUNT = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
return redis.call('ZCARD', key)
"""

# 读取当前窗口求和（清理过期 + 解析 member 求和）
_LUA_GET_SUM = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local members = redis.call('ZRANGEBYSCORE', key, '-inf', '+inf')
local total = 0
for _, m in ipairs(members) do
    local sep = string.find(m, ':', 1, true)
    if sep then
        local val = tonumber(string.sub(m, sep + 1))
        if val then total = total + val end
    end
end
return tostring(total)
"""

# 写入计数型 entry（ZADD + EXPIRE）
_LUA_RECORD_COUNT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local member = ARGV[3]
local cutoff = now - ttl
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl * 2)
return redis.call('ZCARD', key)
"""

# 写入求和型 entry（ZADD + EXPIRE）
_LUA_RECORD_SUM = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local member = ARGV[3]
local cutoff = now - ttl
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl * 2)
local members = redis.call('ZRANGEBYSCORE', key, '-inf', '+inf')
local total = 0
for _, m in ipairs(members) do
    local sep = string.find(m, ':', 1, true)
    if sep then
        local val = tonumber(string.sub(m, sep + 1))
        if val then total = total + val end
    end
end
return tostring(total)
"""


def build_key(group_id: str, limit_type: str, window_sec: int, username: str | None = None) -> str:
    """构造 Redis key。username 存在时为 per-user 级别，否则为 group 级别。"""
    if username:
        return f"rate:{group_id}:user:{username}:{limit_type}:{window_sec}"
    return f"rate:{group_id}:{limit_type}:{window_sec}"


def _cutoff(window_sec: int) -> float:
    return time.time() - window_sec


def _supports_eval_fallback(exc: Exception) -> bool:
    """仅在脚本执行能力缺失时回退到原生命令，其他异常继续按 fail-open 处理。"""
    msg = str(exc).lower()
    return (
        "unknown command" in msg and "eval" in msg
    ) or "script" in msg and "not support" in msg


async def _count_native(redis_client, key: str, window_sec: int) -> int:
    cutoff = _cutoff(window_sec)
    await redis_client.zremrangebyscore(key, 0, cutoff)
    return int(await redis_client.zcard(key))


async def _sum_native(redis_client, key: str, window_sec: int) -> float:
    cutoff = _cutoff(window_sec)
    await redis_client.zremrangebyscore(key, 0, cutoff)
    members = await redis_client.zrange(key, 0, -1)
    total = 0.0
    for member in members:
        sep = member.find(":")
        if sep == -1:
            continue
        try:
            total += float(member[sep + 1 :])
        except ValueError:
            continue
    return total


async def _record_count_native(redis_client, key: str, window_sec: int, request_id: str) -> None:
    now = time.time()
    cutoff = now - window_sec
    await redis_client.zremrangebyscore(key, 0, cutoff)
    await redis_client.zadd(key, {request_id: now})
    await redis_client.expire(key, window_sec * 2)


async def _record_sum_native(
    redis_client, key: str, window_sec: int, request_id: str, value: float
) -> None:
    now = time.time()
    cutoff = now - window_sec
    member = f"{request_id}:{value}"
    await redis_client.zremrangebyscore(key, 0, cutoff)
    await redis_client.zadd(key, {member: now})
    await redis_client.expire(key, window_sec * 2)


async def get_window_count(redis_client, key: str, window_sec: int) -> int:
    """获取滑动窗口内请求计数。Redis 不可用时返回 0（fail open）。"""
    try:
        result = await redis_client.eval(_LUA_GET_COUNT, 1, key, _cutoff(window_sec))
        return int(result)
    except Exception as exc:
        if _supports_eval_fallback(exc):
            try:
                return await _count_native(redis_client, key, window_sec)
            except Exception:
                logger.warning(f"Redis get_window_count 原生命令回退失败，fail open: key={key}")
        logger.warning(f"Redis get_window_count 失败，fail open: key={key}")
        return 0


async def get_window_sum(redis_client, key: str, window_sec: int) -> float:
    """获取滑动窗口内数值总和。Redis 不可用时返回 0（fail open）。"""
    try:
        result = await redis_client.eval(_LUA_GET_SUM, 1, key, _cutoff(window_sec))
        return float(result)
    except Exception as exc:
        if _supports_eval_fallback(exc):
            try:
                return await _sum_native(redis_client, key, window_sec)
            except Exception:
                logger.warning(f"Redis get_window_sum 原生命令回退失败，fail open: key={key}")
        logger.warning(f"Redis get_window_sum 失败，fail open: key={key}")
        return 0.0


async def record_request(redis_client, key: str, window_sec: int, request_id: str) -> None:
    """记录一次请求到滑动窗口。失败静默（不抛异常）。"""
    try:
        now = time.time()
        await redis_client.eval(_LUA_RECORD_COUNT, 1, key, now, window_sec, request_id)
    except Exception as exc:
        if _supports_eval_fallback(exc):
            try:
                await _record_count_native(redis_client, key, window_sec, request_id)
                return
            except Exception:
                logger.warning(f"Redis record_request 原生命令回退失败: key={key}")
        logger.warning(f"Redis record_request 失败: key={key}")


async def record_value(
    redis_client, key: str, window_sec: int, request_id: str, value: float
) -> None:
    """记录一个数值（token 数或金额）到滑动窗口。失败静默（不抛异常）。"""
    try:
        now = time.time()
        member = f"{request_id}:{value}"
        await redis_client.eval(_LUA_RECORD_SUM, 1, key, now, window_sec, member)
    except Exception as exc:
        if _supports_eval_fallback(exc):
            try:
                await _record_sum_native(redis_client, key, window_sec, request_id, value)
                return
            except Exception:
                logger.warning(f"Redis record_value 原生命令回退失败: key={key}")
        logger.warning(f"Redis record_value 失败: key={key}")
