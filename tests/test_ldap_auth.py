"""
LDAP 认证服务单元测试。
使用 unittest.mock 模拟 ldap3，不需要真实 LDAP 服务器。
"""
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))


# ---------------------------------------------------------------------------
# 辅助函数：重新加载 ldap_auth 模块（用于隔离测试环境变量）
# ---------------------------------------------------------------------------

def _reload_ldap_auth(env_vars: dict):
    """在给定环境变量下重新加载 services.ldap_auth 模块，返回模块对象。"""
    # 先移除已缓存的模块，强制重新执行模块级代码
    to_remove = [
        key for key in sys.modules
        if key == "services" or key.startswith("services.")
    ]
    for key in to_remove:
        del sys.modules[key]

    with patch.dict(os.environ, env_vars, clear=False):
        import services.ldap_auth as m  # noqa: PLC0415
    return m


# ---------------------------------------------------------------------------
# 测试：ldap_service 单例在缺少环境变量时应为 None
# ---------------------------------------------------------------------------

def test_ldap_service_none_when_no_env():
    """当 LDAP_* 环境变量未设置时，ldap_service 应为 None。"""
    # 临时清除相关环境变量
    env_patch = {
        "LDAP_SERVER_URL": "",
        "LDAP_BASE_DN": "",
        "LDAP_DOMAIN": "",
    }
    # 移除已有的变量
    saved = {}
    for k in ("LDAP_SERVER_URL", "LDAP_BASE_DN", "LDAP_DOMAIN"):
        saved[k] = os.environ.pop(k, None)

    try:
        mod = _reload_ldap_auth({})
        assert mod.ldap_service is None, "缺少环境变量时 ldap_service 应为 None"
    finally:
        # 恢复原始环境变量
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# 测试：正常 LDAP 认证成功
# ---------------------------------------------------------------------------

def test_authenticate_success():
    """有效凭据 → authenticate() 返回 True。"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None, "环境变量完整时 ldap_service 不应为 None"

    # 模拟 Connection 成功绑定（auto_bind=True 不抛出异常）
    mock_conn = MagicMock()
    with patch("services.ldap_auth.Connection", return_value=mock_conn) as mock_cls:
        result = service.authenticate("alice", "correct_password")

    assert result is True
    mock_conn.unbind.assert_called_once()


# ---------------------------------------------------------------------------
# 测试：LDAP 认证失败（凭据错误）
# ---------------------------------------------------------------------------

def test_authenticate_failure():
    """无效凭据（Connection 抛出异常）→ authenticate() 返回 False。"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    with patch("services.ldap_auth.Connection", side_effect=Exception("Invalid credentials")):
        result = service.authenticate("alice", "wrong_password")

    assert result is False


# ---------------------------------------------------------------------------
# 测试：管理员 fallback key 正确 → True
# ---------------------------------------------------------------------------

def test_authenticate_fallback_key():
    """username=_admin_fallback + 正确的 ADMIN_FALLBACK_KEY → True。"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
        "ADMIN_FALLBACK_KEY": "super_secret_key",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    with patch.dict(os.environ, {"ADMIN_FALLBACK_KEY": "super_secret_key"}):
        result = service.authenticate("_admin_fallback", "super_secret_key")

    assert result is True


# ---------------------------------------------------------------------------
# 测试：管理员 fallback key 错误 → False
# ---------------------------------------------------------------------------

def test_authenticate_fallback_key_wrong():
    """username=_admin_fallback + 错误的 ADMIN_FALLBACK_KEY → False。"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
        "ADMIN_FALLBACK_KEY": "super_secret_key",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    with patch.dict(os.environ, {"ADMIN_FALLBACK_KEY": "super_secret_key"}):
        result = service.authenticate("_admin_fallback", "wrong_key")

    assert result is False


# ---------------------------------------------------------------------------
# 测试：get_user_groups 返回用户所属 AD 组列表
# ---------------------------------------------------------------------------

def test_get_user_groups_returns_list():
    """get_user_groups returns list of group strings"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    # 模拟 conn.entries 中包含 memberOf 属性的条目
    mock_entry = MagicMock()
    mock_entry.memberOf = [
        "CN=GroupA,DC=test,DC=local",
        "CN=GroupB,DC=test,DC=local",
    ]
    mock_conn = MagicMock()
    mock_conn.entries = [mock_entry]

    with patch("services.ldap_auth.Connection", return_value=mock_conn):
        groups = service.get_user_groups("alice", "TEST\\svc_acct", "svc_pwd")

    assert isinstance(groups, list)
    assert groups == [
        "CN=GroupA,DC=test,DC=local",
        "CN=GroupB,DC=test,DC=local",
    ]


def test_get_user_groups_returns_empty_when_no_entries():
    """get_user_groups returns [] when the user is not found in LDAP"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    mock_conn = MagicMock()
    mock_conn.entries = []  # 没有匹配条目

    with patch("services.ldap_auth.Connection", return_value=mock_conn):
        groups = service.get_user_groups("ghost", "TEST\\svc_acct", "svc_pwd")

    assert groups == []


def test_get_user_groups_returns_empty_on_connection_error():
    """get_user_groups returns [] gracefully when Connection raises an exception"""
    env = {
        "LDAP_SERVER_URL": "ldap://fake-dc.test",
        "LDAP_BASE_DN": "DC=test,DC=local",
        "LDAP_DOMAIN": "TEST",
    }
    mod = _reload_ldap_auth(env)
    service = mod.ldap_service
    assert service is not None

    with patch("services.ldap_auth.Connection", side_effect=Exception("Connection refused")):
        groups = service.get_user_groups("alice", "TEST\\svc_acct", "svc_pwd")

    assert groups == []
