from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastcrud import FastCRUD
from db.models import Token
from db.database import engine
from loguru import logger


class AuthMiddleware(BaseHTTPMiddleware):
    AUTH_PREFIXES = ("/v1/",)
    # 可选 API Key 路径：无 key → 放行；有效 key → 注入；无效 key → 401（快速失败）
    AUTH_OPTIONAL_KEY_PATHS = {"/v1/models"}

    @staticmethod
    def _extract_key(headers) -> str | None:
        """
        从请求头提取 API Key，优先级：
        1. x-api-key（OpenAI / Anthropic 风格）
        2. x-goog-api-key（Gemini 风格）
        3. Authorization: Bearer <key>
        """
        if key := headers.get("x-api-key"):
            return key
        if key := headers.get("x-goog-api-key"):
            return key
        auth = headers.get("authorization", "")
        bearer = auth.removeprefix("Bearer ").strip()
        return bearer or None

    @staticmethod
    def _inject_token_state(request: Request, token: dict) -> None:
        """将已验证的 token 信息注入 request.state。"""
        request.state.api_key_authed = True  # sentinel for downstream handlers
        request.state.token_id = token["id"]
        request.state.token_name = token["name"]
        request.state.token_group_id = token.get("group_id")
        request.state.quota_usd = token.get("quota_usd", 0)
        request.state.used_usd = token.get("used_usd", 0)
        request.state.token_username = token.get("username")

    @staticmethod
    async def _validate_key(key: str) -> tuple[dict | None, str, int]:
        """
        查询并验证 API Key。
        返回 (token_dict, error_msg, status_code)：
          - 成功：(token, "", 200)
          - 失败：(None, "error message", 401/503)
        """
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

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 非 /v1/* 路径完全放行
        if not path.startswith(self.AUTH_PREFIXES):
            return await call_next(request)

        # 可选 API Key 路径（如 /v1/models）
        if path in self.AUTH_OPTIONAL_KEY_PATHS:
            # 只检查专用 API Key headers，Authorization Bearer 保留给 endpoint 的 JWT 认证
            api_key = (
                request.headers.get("x-api-key")
                or request.headers.get("x-goog-api-key")
            )
            if api_key:
                token, error_msg, status_code = await self._validate_key(api_key)
                if token is None:
                    return JSONResponse({"error": error_msg}, status_code=status_code)
                self._inject_token_state(request, token)
            # 无专用 key → 放行，由 endpoint 处理 JWT 认证
            # 注意：当前 endpoint 使用 Header(...) 强制依赖，缺失时 FastAPI 返回 422；
            # 统一转换为 401，避免调用方收到不明确的 422。
            # Task 2 修改 endpoint 为可选认证后，此转换可移除。
            response = await call_next(request)
            if response.status_code == 422:
                return JSONResponse({"error": "authentication required"}, status_code=401)
            return response

        # 必须有 API Key 的路径（/v1/* 其余路径）
        key = self._extract_key(request.headers)
        if not key:
            return JSONResponse({"error": "missing api key"}, status_code=401)

        token, error_msg, status_code = await self._validate_key(key)
        if token is None:
            return JSONResponse({"error": error_msg}, status_code=status_code)

        self._inject_token_state(request, token)
        return await call_next(request)
