"""
Streamlit Admin 登录认证模块。

在每个需要保护的 Admin 页面顶部调用 ``require_admin_login()``，
未登录时强制显示登录表单并阻止后续渲染。

用法::

    from auth import require_admin_login

    require_admin_login()
    # 以下代码仅在认证通过后执行
    st.title("管理页面")
"""

import sys
from pathlib import Path

import streamlit as st

# any_gateway 未安装为包，通过 sys.path 导入
_AG_PATH = str(Path(__file__).parent.parent.parent / "any_gateway")
if _AG_PATH not in sys.path:
    sys.path.insert(0, _AG_PATH)

from services.ldap_auth import check_fallback_key, ldap_service  # noqa: E402


def require_admin_login() -> None:
    """在每个 Admin 页面顶部调用，未登录则强制显示登录表单。

    认证通过后将以下值写入 ``st.session_state``：

    - ``admin_authenticated`` (bool): True 表示已登录。
    - ``admin_user`` (str): 登录用户名。
    """
    if st.session_state.get("admin_authenticated"):
        return

    st.title("管理员登录")

    if ldap_service is None:
        st.warning(
            "LDAP 服务未配置（缺少 LDAP_SERVER_URL / LDAP_BASE_DN / LDAP_DOMAIN 环境变量）。\n\n"
            "仅支持通过 `_admin_fallback` + ADMIN_FALLBACK_KEY 的应急登录方式。"
        )

    with st.form("login"):
        username = st.text_input("AD 用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

    if submitted:
        if ldap_service is not None:
            ok = ldap_service.authenticate(username, password)
        else:
            # 无 LDAP 服务时，仅允许 fallback key 登录
            ok = check_fallback_key(username, password)

        if ok:
            st.session_state.admin_authenticated = True
            st.session_state.admin_user = username
            st.rerun()
        else:
            st.error("用户名或密码错误")

    st.stop()
