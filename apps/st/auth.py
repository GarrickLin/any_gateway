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

import httpx
import streamlit as st

from any_gateway.constants import GATEWAY_PORT

_LOGIN_URL = f"http://localhost:{GATEWAY_PORT}/admin/auth/login"


def require_admin_login() -> None:
    """在每个 Admin 页面顶部调用，未登录则强制显示登录表单。

    认证通过后将以下值写入 ``st.session_state``：

    - ``admin_authenticated`` (bool): True 表示已登录。
    - ``admin_user`` (str): 登录用户名。
    """
    if st.session_state.get("admin_authenticated"):
        return

    st.title("管理员登录")

    with st.form("login"):
        username = st.text_input("AD 用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

    if submitted:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    _LOGIN_URL,
                    json={"username": username, "password": password},
                )
            if resp.status_code == 200:
                st.session_state.admin_authenticated = True
                st.session_state.admin_user = username
                st.rerun()
            else:
                detail = resp.json().get("detail", "用户名或密码错误")
                st.error(detail)
        except httpx.RequestError as e:
            st.error(f"无法连接到后端服务（localhost:{GATEWAY_PORT}）：{e}")

    st.stop()
