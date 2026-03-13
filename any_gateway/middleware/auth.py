from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi.responses import JSONResponse
from fastcrud import FastCRUD
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from db.database import engine
from db.models import Token, User

# 导出供测试 patch
from services.rate_limit_redis import get_window_count, get_window_sum  # noqa: F401

_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


class AuthMiddleware(BaseHTTPMiddleware):
    AUTH_PREFIXES = ("/v1/",)
    AUTH_OPTIONAL_KEY_PATHS = {"/v1/models"}

    @staticmethod
    def _extract_dedicated_key(headers) -> str | None:
        return headers.get("x-api-key") or headers.get("x-goog-api-key") or None

    @staticmethod
    def _extract_key(headers) -> str | None:
        if key := AuthMiddleware._extract_dedicated_key(headers):
            return key
        auth = headers.get("authorization", "")
        bearer = auth.removeprefix("Bearer ").strip()
        return bearer or None

    @staticmethod
    def _inject_token_state(request: Request, token: dict) -> None:
        request.state.token_id = token["id"]
        request.state.token_name = token["name"]
        request.state.token_group_id = token.get("group_id")
        request.state.quota_usd = token.get("quota_usd", 0)
        request.state.used_usd = token.get("used_usd", 0)
        request.state.token_username = token.get("username")
        if not hasattr(request.state, "covered_by_package"):
            request.state.covered_by_package = False  # 默认不走套餐

    @staticmethod
    async def _validate_key(key: str) -> tuple[dict | None, str, int]:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                crud = FastCRUD(Token)
                token = await crud.get(session, key=key)
        except Exception as e:
            logger.error(f"Auth DB error: {e}")
            return None, "service unavailable", 503

        if not token:
            return None, "invalid api key", 401
        if token.get("frozen", False):
            return None, "api key is frozen", 401
        if token.get("expires_at"):
            try:
                expires_dt = datetime.fromisoformat(
                    token["expires_at"].replace("Z", "+00:00")
                )
                if datetime.now(timezone.utc) > expires_dt:
                    return None, "api key expired", 401
            except ValueError:
                logger.error(f"expires_at 格式异常，拒绝请求: {token['expires_at']!r}")
                return None, "invalid token", 401
        return token, "", 200

    @staticmethod
    async def _check_type2(username: str | None, type1_error: str | None = None) -> Optional[JSONResponse]:
        """检查 Type 2 账户余额。None=无限放行，>0=有余额放行，0=无余额429。

        type1_error: 若 Type 1 超限时的具体原因，Type 2 也拒绝时优先作为 error 字段返回。
        """
        error_msg = type1_error or "quota exceeded"
        if not username:
            return JSONResponse({"error": error_msg}, status_code=429)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                crud = FastCRUD(User)
                user = await crud.get(session, username=username)
                quota_usd = user.get("quota_usd", 0) if user else 0
                from services.quota import check_account_quota
                if check_account_quota(quota_usd):
                    return None  # 放行
        except Exception as e:
            logger.error(f"Type 2 账户检查异常，fail open: {e}")
            return None  # fail open
        return JSONResponse({"error": error_msg}, status_code=429)

    @staticmethod
    async def _check_limits(request: Request, token: dict) -> Optional[JSONResponse]:
        """
        检查 Type 1（套餐）和 Type 2（账户余额）。
        返回 None 表示放行，返回 JSONResponse(429) 表示拒绝。

        优先级：
        - 有 group → 先检查 Type 1
          - Type 1 通过 → 放行
          - Type 1 超限 → 降级到 Type 2
        - 无 group → 直接 Type 2
        """
        group_id = token.get("group_id")
        username = token.get("username")

        if group_id:
            # Type 1：套餐规则检查
            try:
                from services.rate_limit_service import check_rate_limits
                redis_client = await _get_redis()
                async with AsyncSession(engine, expire_on_commit=False) as session:
                    passed, error_msg = await check_rate_limits(
                        group_id, redis_client, session, username=username
                    )
                if passed:
                    # 检查 group 是否有启用的 quota_limit 规则（有 → 套餐模式）
                    from db.models import RateLimit
                    async with AsyncSession(engine, expire_on_commit=False) as _s:
                        rules_result = await FastCRUD(RateLimit).get_multi(_s, group_id=group_id)
                    has_quota_limit = any(
                        r["limit_type"] == "quota_limit" and r["value"] > 0
                        for r in rules_result.get("data", [])
                    )
                    if has_quota_limit:
                        request.state.covered_by_package = True
                    return None  # 套餐通过，放行
                # 套餐超限 → 降级 Type 2，保存 Type 1 超限原因
                logger.info(f"Type 1 超限 ({error_msg})，降级到 Type 2: username={username}")
                return await AuthMiddleware._check_type2(username, type1_error=error_msg)
            except Exception as e:
                logger.error(f"Type 1 限流检查异常，fail open: {e}")
                return None  # fail open

        # 无 group → Type 2
        return await AuthMiddleware._check_type2(username)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith(self.AUTH_PREFIXES):
            return await call_next(request)

        if path in self.AUTH_OPTIONAL_KEY_PATHS:
            api_key = self._extract_dedicated_key(request.headers)
            if api_key:
                token, error_msg, status_code = await self._validate_key(api_key)
                if token is None:
                    return JSONResponse({"error": error_msg}, status_code=status_code)
                self._inject_token_state(request, token)
            return await call_next(request)

        key = self._extract_key(request.headers)
        if not key:
            return JSONResponse({"error": "missing api key"}, status_code=401)

        token, error_msg, status_code = await self._validate_key(key)
        if token is None:
            return JSONResponse({"error": error_msg}, status_code=status_code)

        # 限流检查（Before 阶段）
        limit_response = await self._check_limits(request, token)
        if limit_response is not None:
            return limit_response

        self._inject_token_state(request, token)
        return await call_next(request)
