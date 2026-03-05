#!/usr/bin/env python3
"""
Mock AD (LDAP) Server for local development.

监听真实 TCP 端口，处理 Simple Bind，支持以下格式：
  - DOMAIN\\username   (ldap_auth.py 当前使用的格式)
  - username@domain
  - 裸用户名

用法：
  USERS_YAML=users.yaml python server.py
  docker compose up mock-ad
"""

import os
import sys

import yaml
from ldaptor.protocols import pureldap
from ldaptor.protocols.ldap import ldaperrors, ldapserver
from twisted.internet import protocol, reactor
from twisted.python import log


def load_config(yaml_path: str) -> tuple[dict, dict]:
    """读取 YAML 配置，返回 (users_by_username, config)。"""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    users = {u["username"].lower(): u for u in config.get("users", [])}
    return users, config


class MockADProtocol(ldapserver.BaseLDAPServer):
    """只处理 Simple Bind 的最小 LDAP 服务实现。"""

    def __init__(self, users: dict, domain: str) -> None:
        ldapserver.BaseLDAPServer.__init__(self)
        self.users = users
        self.domain = domain.lower()

    def handle_LDAPBindRequest(self, request, controls, reply):
        dn = (request.dn or b"").decode("utf-8")
        password = (request.auth or b"").decode("utf-8")

        # 匿名 bind：直接放行
        if not dn:
            reply(pureldap.LDAPBindResponse(resultCode=0))
            return

        username = self._extract_username(dn)
        user = self.users.get(username.lower())

        if user and user.get("password") == password:
            log.msg(f"[OK]   bind success: {username}")
            reply(pureldap.LDAPBindResponse(resultCode=0))
        else:
            log.msg(f"[FAIL] bind failed:  {username}")
            reply(
                pureldap.LDAPBindResponse(
                    resultCode=ldaperrors.LDAPInvalidCredentials.resultCode
                )
            )

    def _extract_username(self, dn: str) -> str:
        """从各种格式的 bind DN 中提取用户名。"""
        if "\\" in dn:
            # DOMAIN\username
            return dn.split("\\", 1)[1]
        if "@" in dn:
            # username@domain
            return dn.split("@")[0]
        if dn.upper().startswith("CN="):
            # CN=username,DC=...
            return dn.split(",")[0][3:]
        return dn


class MockADFactory(protocol.ServerFactory):
    def __init__(self, users: dict, domain: str) -> None:
        self.users = users
        self.domain = domain

    def buildProtocol(self, addr):
        proto = MockADProtocol(self.users, self.domain)
        proto.factory = self
        return proto


def main() -> None:
    config_path = os.getenv("USERS_YAML", "users.yaml")
    users, config = load_config(config_path)

    port = int(config.get("port", 1389))
    domain = config.get("domain", "example.com")

    log.startLogging(sys.stdout)
    log.msg(f"[INIT] Mock AD Server | domain={domain} | port={port}")
    log.msg(f"[INIT] Loaded users: {sorted(users.keys())}")

    factory = MockADFactory(users, domain)
    reactor.listenTCP(port, factory)
    reactor.run()


if __name__ == "__main__":
    main()
