"""
LDAP/AD 认证服务。

使用 Simple Bind 验证 Active Directory 凭据。
支持 ADMIN_FALLBACK_KEY 作为离线应急登录方式。

用法::

    from services.ldap_auth import ldap_service

    if ldap_service is None:
        # 无 LDAP 配置，只能使用 fallback key
        ...
    else:
        ok = ldap_service.authenticate(username, password)
"""

import os

from ldap3 import ALL, SAFE_SYNC, Connection, Server
from ldap3.utils.dn import escape_rdn
from loguru import logger


class LDAPAuthService:
    """封装 ldap3 的 Simple Bind 认证逻辑。

    Args:
        server_url: LDAP 服务器地址，例如 ``"ldap://dc.company.internal"``。
        base_dn:    基础 DN，例如 ``"DC=company,DC=internal"``。
        domain:     NetBIOS 域名，例如 ``"COMPANY"``（用于 NTLM: ``COMPANY\\username``）。
    """

    def __init__(self, server_url: str, base_dn: str, domain: str) -> None:
        self.server = Server(server_url, get_info=ALL)
        self.base_dn = base_dn
        self.domain = domain

    def authenticate(self, username: str, password: str) -> bool:
        """验证用户凭据。

        优先检查 ``_admin_fallback`` 用户名（离线应急登录），
        再通过 LDAP Simple Bind 验证 AD 凭据。

        Args:
            username: 登录名（不含域前缀）。
            password: 明文密码，或 ADMIN_FALLBACK_KEY。

        Returns:
            验证成功返回 ``True``，否则返回 ``False``。
        """
        # 1. 应急 fallback：无需 LDAP 连接
        if username == "_admin_fallback":
            fallback_key = os.getenv("ADMIN_FALLBACK_KEY")
            if fallback_key and password == fallback_key:
                logger.info("管理员通过 ADMIN_FALLBACK_KEY 登录")
                return True
            logger.warning("ADMIN_FALLBACK_KEY 验证失败")
            return False

        # 2. 正常 LDAP Simple Bind
        safe_user = escape_rdn(username)
        bind_user = f"{self.domain}\\{safe_user}"
        try:
            conn = Connection(
                self.server,
                user=bind_user,
                password=password,
                client_strategy=SAFE_SYNC,
                auto_bind=True,   # 自动 open + bind
            )
            conn.unbind()
            return True
        except Exception as e:
            logger.warning(f"LDAP auth failed for {safe_user}: {e}")
            return False

    def get_user_groups(self, username: str, bind_user: str, bind_pwd: str) -> list[str]:
        """查询用户所属 AD 组（可选，用于权限映射）

        Args:
            username:  要查询的登录名（不含域前缀）。
            bind_user: 用于搜索的服务账号 DN 或 ``DOMAIN\\user``。
            bind_pwd:  服务账号密码。

        Returns:
            用户所属 AD 组的 DN 字符串列表；查询失败时返回空列表。
        """
        safe_user = escape_rdn(username)
        try:
            conn = Connection(
                self.server,
                user=bind_user,
                password=bind_pwd,
                client_strategy=SAFE_SYNC,
                auto_bind=True,
            )
            conn.search(
                search_base=self.base_dn,
                search_filter=f"(sAMAccountName={safe_user})",
                attributes=["memberOf"],
            )
            if conn.entries:
                return [str(g) for g in conn.entries[0].memberOf]
            return []
        except Exception as e:
            logger.warning(f"get_user_groups failed for {safe_user}: {e}")
            return []


# ---------------------------------------------------------------------------
# 模块级单例：仅在所有环境变量均已设置时创建
# ---------------------------------------------------------------------------

_server_url = os.getenv("LDAP_SERVER_URL")
_base_dn = os.getenv("LDAP_BASE_DN")
_domain = os.getenv("LDAP_DOMAIN")

if _server_url and _base_dn and _domain:
    ldap_service: LDAPAuthService | None = LDAPAuthService(
        server_url=_server_url,
        base_dn=_base_dn,
        domain=_domain,
    )
    logger.info(f"LDAP 服务已初始化，服务器: {_server_url}")
else:
    ldap_service = None
    logger.warning(
        "LDAP_SERVER_URL / LDAP_BASE_DN / LDAP_DOMAIN 未完整配置，"
        "ldap_service=None，仅支持 ADMIN_FALLBACK_KEY 登录。"
    )
