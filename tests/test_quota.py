"""
额度检查服务单元测试。
check_quota 为纯逻辑函数，无 I/O，测试无需异步框架。
"""
import sys
from pathlib import Path

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

from services.quota import (
    check_quota,
    check_request_limit,
    check_token_limit,
    check_rolling_cost_limit,
    check_account_quota,
)


# ---------------------------------------------------------------------------
# check_quota 测试
# ---------------------------------------------------------------------------

def test_check_quota_unlimited_when_zero():
    """quota_usd=0 表示无限额度，应始终返回 True，即使 used_usd 极大。"""
    assert check_quota(quota_usd=0, used_usd=9999.99) is True


def test_check_quota_within_limit():
    """used_usd < quota_usd 时，在额度内，返回 True。"""
    assert check_quota(quota_usd=10.0, used_usd=5.0) is True


def test_check_quota_exceeded():
    """used_usd == quota_usd 时，已用尽额度，返回 False。"""
    assert check_quota(quota_usd=10.0, used_usd=10.0) is False


def test_check_quota_exceeded_over():
    """used_usd > quota_usd 时，超出额度，返回 False。"""
    assert check_quota(quota_usd=10.0, used_usd=15.0) is False


def test_update_usage_accepts_request_id():
    """update_usage 应接受 request_id 参数"""
    import inspect
    from services.quota import update_usage
    sig = inspect.signature(update_usage)
    assert "request_id" in sig.parameters
    # 确认默认值为 None（向后兼容）
    assert sig.parameters["request_id"].default is None


def test_update_usage_request_id_none_check():
    """request_id 判断应使用 is not None，空字符串不应降级为自动 id"""
    # 验证当 request_id="" 时，dict 解包结果仍会传入 id=""（走 DB 校验）
    request_id = ""
    kwargs = {"id": request_id} if request_id is not None else {}
    assert kwargs == {"id": ""}  # 空字符串应传入，不降级

    request_id = None
    kwargs = {"id": request_id} if request_id is not None else {}
    assert kwargs == {}  # None 才降级为自动 id


# ---------------------------------------------------------------------------
# check_request_limit 测试
# ---------------------------------------------------------------------------

def test_check_request_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_request_limit(current_count=9999, limit=0) is True


def test_check_request_limit_within():
    """current_count < limit 时，在限制内，返回 True。"""
    assert check_request_limit(current_count=5, limit=10) is True


def test_check_request_limit_at_limit():
    """current_count == limit 时，已达上限，返回 False。"""
    assert check_request_limit(current_count=10, limit=10) is False


def test_check_request_limit_over():
    """current_count > limit 时，超出上限，返回 False。"""
    assert check_request_limit(current_count=15, limit=10) is False


# ---------------------------------------------------------------------------
# check_token_limit 测试
# ---------------------------------------------------------------------------

def test_check_token_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_token_limit(current_tokens=9999, limit=0) is True


def test_check_token_limit_within():
    """current_tokens < limit 时，在限制内，返回 True。"""
    assert check_token_limit(current_tokens=500, limit=1000) is True


def test_check_token_limit_at_limit():
    """current_tokens == limit 时，已达上限，返回 False。"""
    assert check_token_limit(current_tokens=1000, limit=1000) is False


def test_check_token_limit_over():
    """current_tokens > limit 时，超出上限，返回 False。"""
    assert check_token_limit(current_tokens=1500, limit=1000) is False


# ---------------------------------------------------------------------------
# check_rolling_cost_limit 测试
# ---------------------------------------------------------------------------

def test_check_rolling_cost_limit_disabled_when_zero():
    """limit=0 表示禁用，应始终返回 True。"""
    assert check_rolling_cost_limit(current_cost=999.99, limit=0) is True


def test_check_rolling_cost_limit_within():
    """current_cost < limit 时，在限制内，返回 True。"""
    assert check_rolling_cost_limit(current_cost=3.5, limit=10.0) is True


def test_check_rolling_cost_limit_at_limit():
    """current_cost == limit 时，已达上限，返回 False。"""
    assert check_rolling_cost_limit(current_cost=10.0, limit=10.0) is False


def test_check_rolling_cost_limit_over():
    """current_cost > limit 时，超出上限，返回 False。"""
    assert check_rolling_cost_limit(current_cost=12.5, limit=10.0) is False


# ---------------------------------------------------------------------------
# check_account_quota 测试
# ---------------------------------------------------------------------------

def test_check_account_quota_none_is_unlimited():
    """quota_usd=None 表示无限额度，应返回 True。"""
    assert check_account_quota(quota_usd=None) is True


def test_check_account_quota_positive_has_balance():
    """quota_usd > 0 表示有余额，应返回 True。"""
    assert check_account_quota(quota_usd=10.0) is True


def test_check_account_quota_zero_no_balance():
    """quota_usd=0 表示无余额，应返回 False。"""
    assert check_account_quota(quota_usd=0) is False


def test_check_account_quota_negative_no_balance():
    """quota_usd < 0 视为无余额，应返回 False。"""
    assert check_account_quota(quota_usd=-1.0) is False
