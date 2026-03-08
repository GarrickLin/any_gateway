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
    # 只有这些前缀需要 API Key 鉴权（其余路径均放行）
    AUTH_PREFIXES = ("/v1/",)
    # /v1/models 无需 API Key（公开模型列表）
    AUTH_SKIP_PATHS = {"/v1/models"}

    async def dispatch(self, request: Request, call_next):
        # 1. 仅对 /v1/* 路径执行 API Key 鉴权，其余路径各有自己的保护机制或无需鉴权
        path = request.url.path
        if path in self.AUTH_SKIP_PATHS or not path.startswith(self.AUTH_PREFIXES):
            return await call_next(request)

        # 2. 提取 API Key
        # 优先 x-api-key header，其次 Authorization: Bearer xxx
        auth_header = request.headers.get("authorization", "")
        bearer_key = auth_header.removeprefix("Bearer").strip()
        key = request.headers.get("x-api-key") or bearer_key
        if not key:
            return JSONResponse({"error": "missing api key"}, status_code=401)

        # 3. 查询数据库验证 Token
        # 每请求查一次 SQLite（无缓存）。团队内部工具，用户数有限，YAGNI。
        # 若未来 QPS 提升，可用 TTLCache 对 key→token_dict 做 60s 短暂缓存。
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                crud = FastCRUD(Token)
                token = await crud.get(session, key=key)
        except Exception as e:
            logger.error(f"Auth DB error: {e}")
            return JSONResponse({"error": "service unavailable"}, status_code=503)

        if not token:
            return JSONResponse({"error": "invalid api key"}, status_code=401)
        if token.get("frozen", False):
            return JSONResponse({"error": "api key is frozen"}, status_code=401)

        # 4. 检查过期时间
        if token.get("expires_at"):
            expires_at_str = token["expires_at"]
            try:
                # 处理 ISO 8601 格式（含 Z 后缀）
                expires_dt = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
                if datetime.now(timezone.utc) > expires_dt:
                    return JSONResponse({"error": "api key expired"}, status_code=401)
            except ValueError:
                logger.error(f"expires_at 格式异常，拒绝请求: {expires_at_str!r}")
                return JSONResponse({"error": "invalid token"}, status_code=401)

        # 5. 注入 token 信息到 request.state
        request.state.token_id = token["id"]
        request.state.token_name = token["name"]
        request.state.token_group_id = token.get("group_id")
        request.state.quota_usd = token.get("quota_usd", 0)
        request.state.used_usd = token.get("used_usd", 0)
        request.state.token_username = token.get("username")

        return await call_next(request)
