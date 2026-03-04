"""
渠道管理页面（存根）。

此文件由 Streamlit 多页面机制自动发现，访问该页面时需要通过 AD 认证。
"""

import sys
from pathlib import Path

import streamlit as st

# 确保 apps/st 在路径中，以便导入 auth 模块
_ST_PATH = str(Path(__file__).parent.parent)
if _ST_PATH not in sys.path:
    sys.path.insert(0, _ST_PATH)

from auth import require_admin_login  # noqa: E402

require_admin_login()

st.title("渠道管理")
st.info("Coming soon")
