"""
tests/test_rate_limit_redis.py
Redis ZSET 精确滑动窗口限流服务的单元测试。
使用 unittest.mock.AsyncMock mock Redis，不真正连接 Redis。
"""
import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

from services.rate_limit_redis import (
    build_key,
    get_window_count,
    get_window_sum,
    record_request,
    record_value,
)


# ---------------------------------------------------------------------------
# build_key 测试（2个）
# ---------------------------------------------------------------------------

def test_build_key_request_limit():
    assert build_key("group123", "request_limit", 60) == "rate:group123:request_limit:60"


def test_build_key_token_limit():
    assert build_key("g1", "token_limit", 3600) == "rate:g1:token_limit:3600"


# ---------------------------------------------------------------------------
# get_window_count 测试（3个）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_window_count_returns_zero():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value=0)
    result = await get_window_count(redis_client, "rate:g1:request_limit:60", 60)
    assert result == 0


@pytest.mark.asyncio
async def test_get_window_count_returns_five():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value=5)
    result = await get_window_count(redis_client, "rate:g1:request_limit:60", 60)
    assert result == 5


@pytest.mark.asyncio
async def test_get_window_count_fail_open():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(side_effect=Exception("Redis connection error"))
    result = await get_window_count(redis_client, "rate:g1:request_limit:60", 60)
    assert result == 0


# ---------------------------------------------------------------------------
# get_window_sum 测试（3个）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_window_sum_returns_zero():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value="0")
    result = await get_window_sum(redis_client, "rate:g1:token_limit:3600", 3600)
    assert result == 0.0


@pytest.mark.asyncio
async def test_get_window_sum_returns_float():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value="15000.5")
    result = await get_window_sum(redis_client, "rate:g1:token_limit:3600", 3600)
    assert result == 15000.5


@pytest.mark.asyncio
async def test_get_window_sum_fail_open():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(side_effect=Exception("Redis connection error"))
    result = await get_window_sum(redis_client, "rate:g1:token_limit:3600", 3600)
    assert result == 0.0


# ---------------------------------------------------------------------------
# record_request 测试（2个）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_request_calls_eval():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value=1)
    await record_request(redis_client, "rate:g1:request_limit:60", 60, "req-abc-123")
    assert redis_client.eval.call_count == 1


@pytest.mark.asyncio
async def test_record_request_silent_on_error():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(side_effect=Exception("Redis connection error"))
    # 不应抛出异常
    await record_request(redis_client, "rate:g1:request_limit:60", 60, "req-abc-123")


# ---------------------------------------------------------------------------
# record_value 测试（2个）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_value_calls_eval():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(return_value="1000.0")
    await record_value(redis_client, "rate:g1:token_limit:3600", 3600, "req-xyz-456", 500.0)
    assert redis_client.eval.call_count == 1


@pytest.mark.asyncio
async def test_record_value_silent_on_error():
    redis_client = AsyncMock()
    redis_client.eval = AsyncMock(side_effect=Exception("Redis connection error"))
    # 不应抛出异常
    await record_value(redis_client, "rate:g1:token_limit:3600", 3600, "req-xyz-456", 500.0)
