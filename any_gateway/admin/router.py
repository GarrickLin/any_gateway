"""
Admin CRUD API 路由。

- 使用 FastCRUD crud_router 自动生成 Token/Channel/UserGroup 的 CRUD 接口。
- 手动编写业务路由：冻结 Token、统计概览、Token 用量 Top10、模型请求 Top10。
- 所有 /admin/* 路由均需要 x-admin-key Header 校验。
"""

import asyncio
import csv
import io
import json
import os
from functools import cmp_to_key
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastcrud import FastCRUD, crud_router
from jose import JWTError
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import async_session_generator
from db.models import (
    AdminUser,
    Channel,
    ChannelCreate,
    ChannelUpdate,
    GroupModelPrice,
    GroupModelPriceCreate,
    GroupModelPriceUpdate,
    ModelPrice,
    ModelPriceCreate,
    ModelPriceUpdate,
    RateLimit,
    RateLimitCreate,
    RateLimitUpdate,
    Token,
    TokenCreate,
    TokenUpdate,
    UsageLog,
    UserGroup,
    UserGroupCreate,
    UserGroupUpdate,
    Voucher,
    VoucherCreate,
    VoucherUpdate,
)
from log_writer import get_request_log_path, read_log, parse_date_str
from services.auth_service import require_auth, require_role, verify_token

# ---------------------------------------------------------------------------
# Admin Key 验证依赖
# ---------------------------------------------------------------------------


async def verify_admin_key(x_admin_key: str = Header(...)) -> None:
    """校验 x-admin-key header，不匹配则返回 403。"""
    admin_key = os.environ.get("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        logger.warning("Admin key 校验失败")
        raise HTTPException(status_code=403, detail="Invalid admin key")


async def require_admin_access(
    authorization: str = Header(default=""),
    x_admin_key: str = Header(default=""),
) -> None:
    """统一 Admin 鉴权依赖，支持两种方式（任一满足即可）：

    1. ``x-admin-key`` header —— 程序化 / Legacy 访问。
    2. ``Authorization: Bearer <JWT>`` —— 前端登录后的 JWT（role 须为 admin 或 superadmin）。
    """
    # 方式一：x-admin-key 静态密钥
    admin_key = os.environ.get("ADMIN_KEY", "")
    if x_admin_key and admin_key and x_admin_key == admin_key:
        return

    # 方式二：JWT Bearer token
    if authorization.startswith("Bearer "):
        token_str = authorization[len("Bearer "):]
        try:
            payload = verify_token(token_str)
        except JWTError:
            raise HTTPException(status_code=401, detail="Token 无效或已过期")
        role = payload.get("role", "user")
        if role in ("admin", "superadmin"):
            return
        raise HTTPException(status_code=403, detail="Permission denied: 需要 admin 或 superadmin 角色")

    raise HTTPException(status_code=403, detail="需要 x-admin-key 或有效的 Admin JWT")


# ---------------------------------------------------------------------------
# FastCRUD 自动生成的 CRUD 路由
# fastcrud 的 *_deps 参数接受可调用对象（函数），不是 Depends() 包装对象。
# ---------------------------------------------------------------------------

_common_deps = [require_admin_access]
_user_deps = [require_auth]

token_router: APIRouter = crud_router(
    session=async_session_generator,
    model=Token,
    create_schema=TokenCreate,
    update_schema=TokenUpdate,
    path="/user/tokens",
    tags=["User: Tokens"],
    # create/read_multi/delete 端点单独定义：
    #   create    —— 需返回含 key 的完整 Token
    #   read_multi/delete/db_delete —— 需按登录用户过滤，仅能操作自己的 Token
    deleted_methods=["create", "read_multi", "delete", "db_delete"],
    read_deps=_user_deps,
    update_deps=_user_deps,
)

channel_router: APIRouter = crud_router(
    session=async_session_generator,
    model=Channel,
    create_schema=ChannelCreate,
    update_schema=ChannelUpdate,
    path="/admin/channels",
    tags=["Admin: Channels"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

group_router: APIRouter = crud_router(
    session=async_session_generator,
    model=UserGroup,
    create_schema=UserGroupCreate,
    update_schema=UserGroupUpdate,
    path="/admin/groups",
    tags=["Admin: Groups"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

# ---------------------------------------------------------------------------
# 手动业务路由
# ---------------------------------------------------------------------------

# 无需 admin key 的认证路由（登录端点本身就是鉴权入口）
auth_router = APIRouter(prefix="/admin", tags=["Admin: Auth"])

# /auth/me 路由（无 /admin 前缀，需要 Bearer JWT）
me_router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@auth_router.post("/auth/login", summary="Admin 登录（LDAP / fallback 认证）")
async def admin_login(
    body: LoginRequest,
    session: AsyncSession = Depends(async_session_generator),
) -> dict[str, str]:
    """通过 LDAP 或 ADMIN_FALLBACK_KEY 验证管理员凭据。

    - LDAP 已配置时走 AD Simple Bind。
    - LDAP 未配置时仅允许 ``_admin_fallback`` + ``ADMIN_FALLBACK_KEY`` 应急登录。

    Returns:
        ``{"access_token": "<jwt>", "token_type": "bearer", "role": "<role>"}``
        认证成功；否则返回 401。
    """
    from services.ldap_auth import check_fallback_key, ldap_service
    from services.auth_service import create_access_token, get_user_role

    is_fallback = False
    if ldap_service is not None:
        ok = ldap_service.authenticate(body.username, body.password)
        # fallback key 在 ldap_service.authenticate 内部也会检查
        if ok and body.username == "_admin_fallback":
            is_fallback = True
    else:
        ok = check_fallback_key(body.username, body.password)
        if ok:
            is_fallback = True

    if not ok:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # fallback 应急管理员固定为 superadmin
    if is_fallback:
        role = "superadmin"
    else:
        role = await get_user_role(body.username, session)

    # 懒加载：首次登录时创建 User 并加入 default 分组（fallback 用户跳过）
    if not is_fallback:
        from services.auth_service import lazy_create_user
        await lazy_create_user(body.username, session)
        await session.commit()

    token = create_access_token(body.username, role)
    return {"access_token": token, "token_type": "bearer", "role": role}


@me_router.get("/my-status", summary="获取当前用户状态（余额 + 分组限流剩余）")
async def get_my_status(
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    import os
    import redis.asyncio as aioredis
    from db.models import User, UserGroup, RateLimit
    from services.auth_service import get_visible_groups
    from services.rate_limit_redis import build_key, get_window_count, get_window_sum

    username = user["username"]

    # 1. 获取用户余额
    crud_user = FastCRUD(User)
    db_user = await crud_user.get(session, username=username)
    quota_usd = db_user.get("quota_usd") if db_user else 0
    used_usd = db_user.get("used_usd", 0) if db_user else 0

    # 2. 获取分组：管理员看全部分组，普通用户只看可见分组
    role = user.get("role", "user")
    if role in ("admin", "superadmin"):
        result = await session.execute(
            select(UserGroup).order_by(UserGroup.priority.desc())
        )
        groups = result.scalars().all()
    else:
        groups = await get_visible_groups(username, session)

    # 3. 尝试连接 Redis（不可用时 fail open）
    redis_client = None
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
    except Exception:
        pass

    # 4. 构建每个分组的限流状态
    crud_rl = FastCRUD(RateLimit)
    groups_status = []
    for group in groups:
        rl_result = await crud_rl.get_multi(session, group_id=group.id)
        rules = rl_result.get("data", [])
        rules_status = []
        for rule in rules:
            if rule["value"] <= 0:
                continue
            key = build_key(group.id, rule["limit_type"], rule["window_sec"], username)
            try:
                if rule["limit_type"] == "request_limit":
                    current = await get_window_count(redis_client, key, rule["window_sec"]) if redis_client else 0
                else:
                    current = await get_window_sum(redis_client, key, rule["window_sec"]) if redis_client else 0
            except Exception:
                current = 0
            limit = rule["value"]
            remaining_pct = max(0.0, (limit - current) / limit * 100) if limit > 0 else 0.0
            rules_status.append({
                "rule_id": rule["id"],
                "limit_type": rule["limit_type"],
                "window_sec": rule["window_sec"],
                "limit": limit,
                "current": current,
                "remaining_pct": round(remaining_pct, 1),
            })

        if not rules_status:
            continue  # 无有效规则的分组不展示

        groups_status.append({
            "group_id": group.id,
            "group_name": group.name,
            "is_all_visible": group.all_visible,
            "rate_limits": rules_status,
        })

    return {
        "quota_usd": quota_usd,
        "used_usd": used_usd,
        "groups": groups_status,
    }


@me_router.get("/me", summary="获取当前登录用户信息")
async def get_me(
    user: dict = Depends(require_auth),
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    from db.models import User
    crud = FastCRUD(User)
    db_user = await crud.get(session, username=user.get("username"))
    return {
        **user,
        "quota_usd": db_user.get("quota_usd") if db_user else 0,
        "used_usd": db_user.get("used_usd", 0) if db_user else 0,
    }


# ---------------------------------------------------------------------------
# 统计响应模型（user_router 和 admin_router 共用）
# ---------------------------------------------------------------------------


class OverviewResponse(BaseModel):
    total_cost_usd: float
    actual_cost_usd: float
    request_count: int
    total_token_usage: int
    date: str


class TokenStatsItem(BaseModel):
    token_id: str | None
    username: str | None
    token_name: str | None
    total_cost_usd: float
    request_count: int


class ModelStatsItem(BaseModel):
    model: str | None
    request_count: int


class UsageStatsItem(BaseModel):
    date: str
    username: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    request_count: int
    total_cost_usd: float


# ---------------------------------------------------------------------------
# 用户路由（任何已登录用户均可访问）
# ---------------------------------------------------------------------------

user_router = APIRouter(
    prefix="/user",
    tags=["User: Tokens"],
    dependencies=[Depends(require_auth)],
)


# ------ 创建 Token（需返回含 key 的完整记录）-----------------------------------


@user_router.get("/tokens", summary="列出当前用户的 Token")
async def list_my_tokens(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> dict:
    """仅返回当前登录用户自己创建的 Token。"""
    stmt = select(Token).where(Token.username == current_user["username"]).order_by(Token.created_at.desc())
    result = await session.execute(stmt)
    tokens = list(result.scalars().all())
    return {"data": [t.model_dump() for t in tokens], "total": len(tokens)}


@user_router.post("/tokens", summary="创建 Token（返回含 key 的完整记录）", response_model=Token)
async def create_token(
    body: TokenCreate,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> Token:
    """创建 Token 并返回完整记录（含一次性明文 key）。

    FastCRUD crud_router 的 create 端点响应 schema 为 TokenCreate，不含 key 字段，
    因此单独实现此端点以确保前端能获取到生成的 key。
    username 自动从 JWT 注入，用户只能为自己创建 Token。
    """
    token = Token(**body.model_dump())
    token.username = current_user["username"]
    session.add(token)
    await session.commit()
    await session.refresh(token)
    logger.info(f"Token [{token.name}] 已创建，id={token.id}，用户：{current_user['username']}")
    return token


@user_router.delete("/tokens/{token_id}", summary="删除 Token（仅限自己的）")
async def delete_my_token(
    token_id: str,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> dict:
    """删除指定 Token，仅允许删除自己的 Token（admin/superadmin 可删除任意 Token）。"""
    crud = FastCRUD(Token)
    token = await crud.get(session, id=token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if token["username"] != current_user["username"] and current_user["role"] not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权删除他人的 Token")
    await crud.db_delete(session, id=token_id)
    logger.info(f"Token {token_id} 已删除，操作者：{current_user['username']}")
    return {"ok": True}


# ------ 冻结 / 解冻 Token --------------------------------------------------


class FreezeRequest(BaseModel):
    frozen: bool


@user_router.post("/tokens/{token_id}/freeze", summary="冻结 / 解冻 Token")
@user_router.patch("/tokens/{token_id}/freeze", summary="冻结 / 解冻 Token")
# 同时支持 POST 和 PATCH，POST 用于兼容 spec 要求，PATCH 为 REST 语义
async def freeze_token(
    token_id: str,
    body: FreezeRequest,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> dict[str, Any]:
    """将指定 Token 设置为冻结（frozen=True）或解冻（frozen=False）。
    仅允许操作自己的 Token（admin/superadmin 可操作任意 Token）。
    """
    crud = FastCRUD(Token)
    # 先检查 token 是否存在
    token = await crud.get(session, id=token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if token["username"] != current_user["username"] and current_user["role"] not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权操作他人的 Token")

    # 更新冻结状态
    await crud.update(session, object={"frozen": body.frozen}, id=token_id)
    # 返回合并结果，避免第二次 DB 查询
    updated = await crud.get(session, id=token_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated token")
    logger.info(f"Token {token_id} frozen={body.frozen}，操作者：{current_user['username']}")
    return updated


@user_router.get("/logs/{request_id}/messages", summary="查询请求消息详情（当前用户）")
async def get_log_messages_user(
    request_id: str,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
):
    # 1. 先查 DB 做权限校验
    result = await session.execute(select(UsageLog).where(UsageLog.id == request_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="日志记录不存在")
    if log.username != current_user["username"]:
        raise HTTPException(status_code=403, detail="无权访问此日志")

    # 2. 权限通过后复用共享读取函数
    return await _get_request_messages(request_id, session)


class RedeemRequest(BaseModel):
    code: str


@user_router.post("/vouchers/redeem", summary="通过券码充值")
async def redeem_voucher(
    body: RedeemRequest,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> dict:
    """用户输入消费券码充值，成功则将 amount_usd 加入 User.quota_usd。"""
    from datetime import datetime, timezone
    from db.models import Voucher, User

    result = await session.execute(
        select(Voucher).where(Voucher.code == body.code, Voucher.used == False)  # noqa: E712
    )
    voucher = result.scalar_one_or_none()
    if voucher is None:
        raise HTTPException(status_code=404, detail="券码不存在或已被使用")

    if voucher.expires_at:
        now = datetime.now(timezone.utc).isoformat()
        if now > voucher.expires_at:
            raise HTTPException(status_code=400, detail="券码已过期")

    username = current_user["username"]
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    voucher.used = True
    voucher.used_at = now_str
    voucher.used_by = username
    session.add(voucher)

    user_result = await session.execute(select(User).where(User.username == username))
    user = user_result.scalar_one_or_none()
    if user is None:
        user = User(username=username, quota_usd=voucher.amount_usd)
        session.add(user)
    else:
        user.quota_usd = (user.quota_usd or 0) + voucher.amount_usd
        session.add(user)

    await session.commit()
    logger.info(f"用户 {username} 兑换消费券，充值 ${voucher.amount_usd}")
    return {"ok": True, "amount_usd": voucher.amount_usd, "new_quota_usd": user.quota_usd}


@user_router.get("/groups", summary="列出当前用户可见分组（供 Token 绑定选择）")
async def list_groups_for_user(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> list[dict]:
    """返回当前用户可见的分组（显式 membership + all_visible），供创建/编辑 Token 时选择绑定分组。"""
    from services.auth_service import get_visible_groups
    groups = await get_visible_groups(current_user["username"], session)
    return [{"id": g.id, "name": g.name} for g in groups]


@user_router.get("/logs", summary="查询当前用户的请求日志")
async def list_my_logs(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
    page: int = 1,
    page_size: int = 20,
    model: str | None = None,
    status: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """仅返回当前用户名下所有 Token 的日志。"""
    return await _query_logs(
        session=session,
        page=page,
        page_size=page_size,
        model=model,
        status=status,
        start_date=start_date,
        end_date=end_date,
        username=current_user["username"],
    )



@user_router.get("/stats/overview", summary="今日整体统计（当前用户）")
async def user_stats_overview(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
    start_at: str | None = None,
    end_at: str | None = None,
) -> OverviewResponse:
    """返回当前用户在筛选范围内的总费用（USD）、请求数和 Token 用量。"""
    stmt = select(
        func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        func.coalesce(
            func.sum(UsageLog.cost_usd).filter(UsageLog.covered_by_package == False),  # noqa: E712
            0,
        ).label("actual_cost_usd"),
        func.count(UsageLog.id).label("request_count"),
        func.coalesce(func.sum(_total_token_usage_expr()), 0).label("total_token_usage"),
    )
    stmt = _apply_stats_time_filters(stmt, start_at=start_at, end_at=end_at)
    stmt = _apply_stats_username_filter(stmt, username=current_user["username"])
    result = await session.execute(stmt)
    row = result.one()
    return OverviewResponse(
        total_cost_usd=float(row.total_cost_usd),
        actual_cost_usd=float(row.actual_cost_usd),
        request_count=int(row.request_count),
        total_token_usage=int(row.total_token_usage),
        date=_today_prefix(),
    )


@user_router.get("/stats/usage", summary="按日期和模型统计当前用户用量")
async def user_stats_usage(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
    start_at: str | None = None,
    end_at: str | None = None,
    timezone: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    return await _list_usage_stats(
        session,
        timezone_name=timezone,
        start_at=start_at,
        end_at=end_at,
        username=current_user["username"],
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@user_router.get("/stats/usage/export", summary="导出当前用户用量统计 CSV")
async def user_stats_usage_export(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
    start_at: str | None = None,
    end_at: str | None = None,
    timezone: str | None = None,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> Response:
    return await _export_usage_stats_csv(
        session,
        timezone_name=timezone,
        start_at=start_at,
        end_at=end_at,
        username=current_user["username"],
        sort_by=sort_by,
        sort_order=sort_order,
        include_username=False,
    )


@user_router.get("/stats/tokens", summary="Top 10 Token 用量（当前用户）")
async def user_stats_tokens(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
) -> list[TokenStatsItem]:
    """返回当前用户今日费用 Top 10 的 Token（按 cost_usd 降序），含 Token 名称。"""
    today = _today_prefix()
    stmt = (
        select(
            UsageLog.token_id,
            UsageLog.username,
            Token.name.label("token_name"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
            func.count(UsageLog.id).label("request_count"),
        )
        .outerjoin(Token, UsageLog.token_id == Token.id)
        .where(
            UsageLog.created_at.like(f"{today}%"),
            UsageLog.username == current_user["username"],
        )
        .group_by(UsageLog.token_id, UsageLog.username, Token.name)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        TokenStatsItem(
            token_id=row.token_id,
            username=row.username,
            token_name=row.token_name,
            total_cost_usd=float(row.total_cost_usd),
            request_count=int(row.request_count),
        )
        for row in rows
    ]


@user_router.get("/stats/models", summary="Top 10 模型请求量（当前用户）")
async def user_stats_models(
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_auth),
    start_at: str | None = None,
    end_at: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> dict:
    """返回当前用户按模型聚合的分页请求统计。"""
    return await _list_model_stats(
        session,
        start_at=start_at,
        end_at=end_at,
        username=current_user["username"],
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ---------------------------------------------------------------------------
# Admin 路由（需要 admin 或 superadmin 角色）
# ---------------------------------------------------------------------------

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_access)],
)


# ------ 从上游拉取模型列表 --------------------------------------------------


@admin_router.post("/channels/{channel_id}/fetch-models", summary="从上游拉取模型列表")
async def fetch_channel_models(
    channel_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    """向上游 API 发送 GET /models 请求，将返回的模型列表存储到 Channel.models（JSON 格式）。"""
    crud = FastCRUD(Channel)
    channel = await crud.get(session, id=channel_id)
    # FastCRUD.get() 返回 dict | None（无 schema_to_select 时）
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    # 向上游拉取模型
    provider = (channel.get("provider") or "").lower()
    base = channel["base_url"].rstrip("/")

    # 各协议的模型列表端点路径
    if provider == "anthropic" and not base.endswith("/v1"):
        models_url = f"{base}/v1/models"
    elif provider == "gemini" and "/v1" not in base:
        models_url = f"{base}/v1beta/models"
    else:
        models_url = f"{base}/models"

    # 各协议的认证头
    if provider == "anthropic":
        headers = {
            "x-api-key": channel["api_key"],
        }
    elif provider == "gemini":
        headers = {"x-goog-api-key": channel["api_key"]}
    else:
        headers = {"Authorization": f"Bearer {channel['api_key']}"}

    logger.info(f"fetch-models → {models_url}  provider={provider}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(models_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        logger.info(f"fetch-models 响应 keys={list(data.keys()) if isinstance(data, dict) else type(data)}")

        # 支持 OpenAI 格式（data 字段）和其他格式
        if "data" in data:
            models = data["data"]
        elif "models" in data:
            models = data["models"]
        else:
            models = []
            logger.warning(f"fetch-models 未识别的响应格式，raw={str(data)[:300]}")

        if not models:
            logger.warning(f"fetch-models 返回空模型列表，channel={channel_id}")

        # Gemini 原生格式规范化：name="models/gemini-xxx"，过滤仅支持 generateContent 的模型
        if provider == "gemini":
            normalized = []
            for m in models:
                if not isinstance(m, dict):
                    continue
                methods = m.get("supportedGenerationMethods") or []
                if "generateContent" not in methods:
                    continue
                model_id = (m.get("name") or "").removeprefix("models/")
                if model_id:
                    normalized.append({"id": model_id, "object": "model", "created": 0, "owned_by": "gemini"})
            models = normalized

        # 截断过大的模型列表
        MAX_MODELS = 100000
        if len(models) > MAX_MODELS:
            logger.warning(f"Channel {channel_id} 返回 {len(models)} 个模型，截断至 {MAX_MODELS}")
            models = models[:MAX_MODELS]

        logger.info(f"fetch-models 保存 {len(models)} 个模型到 channel={channel_id}")

        # 存储为 JSON string
        models_json = json.dumps(models, ensure_ascii=False)
        await crud.update(session, object={"models": models_json}, id=channel_id)

        return {"ok": True, "count": len(models), "models": models}

    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        logger.error(f"fetch-models 上游错误 {e.response.status_code}: {body}")
        raise HTTPException(status_code=502, detail=f"上游返回 {e.response.status_code}: {body}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"连接上游失败: {str(e)}")


# ------ 日志查询接口 ---------------------------------------------------------


async def _get_request_messages(request_id: str, session: AsyncSession) -> dict:
    """
    根据 request_id 从 DB 查 created_at，推导文件路径，读取消息内容。
    DB 记录或文件不存在时抛出 HTTPException。
    """
    result = await session.execute(select(UsageLog).where(UsageLog.id == request_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="日志记录不存在")

    date_str = parse_date_str(log.created_at)
    path = get_request_log_path(request_id, date_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="消息文件不存在")

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, read_log, path)
    return data


async def _query_logs(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    model: str | None = None,
    token_id: str | None = None,
    status: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    username: str | None = None,
) -> dict:
    """日志查询核心逻辑，admin 和 user 端点共用。username 非空时限定到该用户。"""
    stmt = (
        select(UsageLog, Token.name.label("token_name"), Token.username.label("token_username"))
        .outerjoin(Token, UsageLog.token_id == Token.id)
    )

    if model:
        stmt = stmt.where(UsageLog.model == model)
    if token_id:
        stmt = stmt.where(UsageLog.token_id == token_id)
    if username:
        # 优先匹配冗余存储的 username，兼容 Token 已删除的旧记录
        stmt = stmt.where(
            (UsageLog.username == username) | (Token.username == username)
        )
    if status:
        if status >= 500:
            stmt = stmt.where(UsageLog.status >= 500)
        elif status >= 400:
            stmt = stmt.where(UsageLog.status >= 400, UsageLog.status < 500)
        else:
            stmt = stmt.where(UsageLog.status == status)
    if start_date:
        stmt = stmt.where(UsageLog.created_at >= start_date)
    if end_date:
        stmt = stmt.where(UsageLog.created_at <= end_date + "T23:59:59")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(UsageLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).all()

    return {
        "data": [
            {
                **log.model_dump(),
                "token_name": token_name,
                # UsageLog.username 冗余存储，Token 删除后仍可追溯；兜底取 Token.username（兼容旧数据）
                "username": log.username or token_username,
            }
            for log, token_name, token_username in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@admin_router.get("/logs/{request_id}/messages", summary="查询请求消息详情（管理员）")
async def get_log_messages_admin(
    request_id: str,
    session: AsyncSession = Depends(async_session_generator),
):
    return await _get_request_messages(request_id, session)


@admin_router.get("/logs", summary="查询请求日志")
async def list_logs(
    session: AsyncSession = Depends(async_session_generator),
    page: int = 1,
    page_size: int = 20,
    model: str | None = None,
    token_id: str | None = None,
    status: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    username: str | None = None,
) -> dict:
    """分页查询 usage_logs，支持按模型、token_id、用户名、状态码、日期范围过滤。"""
    return await _query_logs(
        session=session,
        page=page,
        page_size=page_size,
        model=model,
        token_id=token_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        username=username,
    )


# ------ 统计接口 ------------------------------------------------------------


def _today_prefix() -> str:
    """返回今日日期前缀（ISO 8601，UTC，用于 LIKE 查询）。"""
    return datetime.now(timezone.utc).date().isoformat()  # e.g. "2026-03-04"


def _get_usage_timezone(timezone_name: str | None) -> ZoneInfo:
    """解析 usage 统计使用的时区，非法值返回 422。"""
    try:
        return ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Invalid timezone") from exc


def _parse_usage_created_at(value: str | datetime) -> datetime:
    """解析 UsageLog.created_at，兼容带 Z 的 UTC 字符串。"""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_utc_z_iso(dt: datetime) -> str:
    """把带时区的 datetime 格式化成 UTC Z 字符串。"""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_usage_default_window(timezone_obj: ZoneInfo) -> tuple[str, str]:
    """按客户端时区计算默认的“今天” UTC 过滤窗口。"""
    local_today = datetime.now(timezone_obj).date()
    start_local = datetime.combine(local_today, time.min, tzinfo=timezone_obj)
    end_local = datetime.combine(local_today, time(23, 59, 59), tzinfo=timezone_obj)
    return _to_utc_z_iso(start_local), _to_utc_z_iso(end_local)


def _total_token_usage_expr():
    """总 Token 用量 = input + output + cache read + cache write。"""
    return (
        UsageLog.input_tokens
        + UsageLog.output_tokens
        + UsageLog.cache_read_tokens
        + UsageLog.cache_creation_tokens
    )


def _apply_stats_time_filters(stmt, start_at: str | None = None, end_at: str | None = None):
    """统计接口时间过滤；未指定范围时保持旧行为，仅统计今日。"""
    if start_at or end_at:
        if start_at:
            stmt = stmt.where(UsageLog.created_at >= start_at)
        if end_at:
            stmt = stmt.where(UsageLog.created_at <= end_at)
        return stmt
    return stmt.where(UsageLog.created_at.like(f"{_today_prefix()}%"))


def _apply_stats_username_filter(stmt, username: str | None = None):
    """统计接口用户名过滤。"""
    if username:
        stmt = stmt.where(UsageLog.username == username)
    return stmt


def _build_usage_rows_stmt(
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
):
    """构造 usage 明细查询，保留 SQL 层时间与用户名过滤。"""
    stmt = select(
        UsageLog.created_at,
        UsageLog.username,
        UsageLog.model,
        UsageLog.input_tokens,
        UsageLog.output_tokens,
        UsageLog.cache_read_tokens,
        UsageLog.cache_creation_tokens,
        UsageLog.cost_usd,
    )
    stmt = _apply_stats_time_filters(stmt, start_at=start_at, end_at=end_at)
    stmt = _apply_stats_username_filter(stmt, username=username)
    return stmt


def _aggregate_usage_rows(rows, timezone_obj: ZoneInfo) -> list[dict[str, Any]]:
    """按本地日期 + 用户名 + 模型聚合 usage 明细行。"""
    buckets: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    for row in rows:
        local_date = _parse_usage_created_at(row.created_at).astimezone(timezone_obj).date().isoformat()
        key = (local_date, row.username, row.model)
        bucket = buckets.setdefault(
            key,
            {
                "date": local_date,
                "username": row.username,
                "model": row.model,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "request_count": 0,
                "total_cost_usd": 0.0,
            },
        )
        bucket["input_tokens"] += int(row.input_tokens or 0)
        bucket["output_tokens"] += int(row.output_tokens or 0)
        bucket["cache_read_tokens"] += int(row.cache_read_tokens or 0)
        bucket["cache_creation_tokens"] += int(row.cache_creation_tokens or 0)
        bucket["request_count"] += 1
        bucket["total_cost_usd"] += float(row.cost_usd or 0)
    return list(buckets.values())


def _compare_usage_rows(left: dict[str, Any], right: dict[str, Any], sort_by: str, sort_order: str) -> int:
    """usage 聚合结果比较器：主排序字段可升降序，次级保持 username/model 升序。"""
    def _value(item: dict[str, Any], field: str):
        value = item.get(field)
        return "" if value is None else value

    def _compare_values(a, b) -> int:
        return (a > b) - (a < b)

    primary_cmp = _compare_values(_value(left, sort_by), _value(right, sort_by))
    if primary_cmp:
        return primary_cmp if sort_order == "asc" else -primary_cmp

    username_cmp = _compare_values(_value(left, "username"), _value(right, "username"))
    if username_cmp:
        return username_cmp

    model_cmp = _compare_values(_value(left, "model"), _value(right, "model"))
    if model_cmp:
        return model_cmp

    return _compare_values(_value(left, "date"), _value(right, "date"))


def _sort_usage_rows(rows: list[dict[str, Any]], sort_by: str | None = None, sort_order: str | None = None) -> list[dict[str, Any]]:
    """按白名单字段为 usage 聚合结果排序。"""
    allowed = {
        "date",
        "username",
        "model",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "request_count",
        "total_cost_usd",
    }
    sort_key = sort_by or "date"
    if sort_key not in allowed:
        sort_key = "date"
    sort_direction = sort_order or "desc"
    return sorted(
        rows,
        key=cmp_to_key(lambda left, right: _compare_usage_rows(left, right, sort_key, sort_direction)),
    )


async def _load_usage_stats(
    session: AsyncSession,
    *,
    timezone_name: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
) -> list[dict[str, Any]]:
    """查询并按客户端时区聚合 usage 数据。"""
    tz = _get_usage_timezone(timezone_name)
    if start_at or end_at:
        effective_start_at, effective_end_at = start_at, end_at
    else:
        effective_start_at, effective_end_at = _build_usage_default_window(tz)
    stmt = _build_usage_rows_stmt(start_at=effective_start_at, end_at=effective_end_at, username=username)
    rows = (await session.execute(stmt)).all()
    return _aggregate_usage_rows(rows, tz)


async def _list_usage_stats(
    session: AsyncSession,
    *,
    timezone_name: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    """分页返回 usage 聚合统计。"""
    rows = await _load_usage_stats(
        session,
        timezone_name=timezone_name,
        start_at=start_at,
        end_at=end_at,
        username=username,
    )
    rows = _sort_usage_rows(rows, sort_by=sort_by, sort_order=sort_order)
    total = len(rows)
    rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    data = [
        UsageStatsItem(**row).model_dump()
        for row in rows
    ]
    return {
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _export_usage_stats_csv(
    session: AsyncSession,
    *,
    timezone_name: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    include_username: bool = True,
) -> Response:
    """导出 usage 聚合统计 CSV。"""
    rows = await _load_usage_stats(
        session,
        timezone_name=timezone_name,
        start_at=start_at,
        end_at=end_at,
        username=username,
    )
    rows = _sort_usage_rows(rows, sort_by=sort_by, sort_order=sort_order)

    output = io.StringIO()
    writer = csv.writer(output)
    header = [
        "date",
        "model",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "request_count",
        "total_cost_usd",
    ]
    if include_username:
        header = ["date", "username"] + header[1:]
    writer.writerow(header)

    for row in rows:
        values = [
            row["date"],
            row["model"] or "",
            int(row["input_tokens"]),
            int(row["output_tokens"]),
            int(row["cache_read_tokens"]),
            int(row["cache_creation_tokens"]),
            int(row["request_count"]),
            float(row["total_cost_usd"]),
        ]
        if include_username:
            values = [row["date"], row["username"] or ""] + values[1:]
        writer.writerow(values)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dashboard-usage.csv"'},
    )


def _build_model_stats_agg(start_at: str | None = None, end_at: str | None = None, username: str | None = None):
    """构造按模型聚合的统计查询。"""
    stmt = select(
        UsageLog.model.label("model"),
        func.count(UsageLog.id).label("request_count"),
    )
    stmt = _apply_stats_time_filters(stmt, start_at=start_at, end_at=end_at)
    stmt = _apply_stats_username_filter(stmt, username=username)
    return stmt.group_by(UsageLog.model)


def _apply_model_sort(stmt, subquery, sort_by: str | None = None, sort_order: str | None = None):
    """按白名单字段为模型统计结果排序。"""
    allowed = {
        "model": subquery.c.model,
        "request_count": subquery.c.request_count,
    }
    column = allowed.get(sort_by or "", subquery.c.request_count)
    order_fn = asc if sort_order == "asc" else desc
    return stmt.order_by(order_fn(column), asc(subquery.c.model))


async def _list_model_stats(
    session: AsyncSession,
    *,
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> dict:
    """分页返回按模型聚合的统计结果。"""
    agg = _build_model_stats_agg(start_at=start_at, end_at=end_at, username=username)
    subquery = agg.subquery()

    count_stmt = select(func.count()).select_from(subquery)
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = select(subquery)
    stmt = _apply_model_sort(stmt, subquery, sort_by=sort_by, sort_order=sort_order)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).all()

    return {
        "data": [
            ModelStatsItem(model=row.model, request_count=int(row.request_count)).model_dump()
            for row in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@admin_router.get("/stats/overview", summary="今日整体统计")
async def stats_overview(
    session: AsyncSession = Depends(async_session_generator),
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
) -> OverviewResponse:
    """返回筛选范围内总费用（USD）、请求数和 Token 用量。"""
    stmt = select(
        func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
        func.coalesce(
            func.sum(UsageLog.cost_usd).filter(UsageLog.covered_by_package == False),  # noqa: E712
            0,
        ).label("actual_cost_usd"),
        func.count(UsageLog.id).label("request_count"),
        func.coalesce(func.sum(_total_token_usage_expr()), 0).label("total_token_usage"),
    )
    stmt = _apply_stats_time_filters(stmt, start_at=start_at, end_at=end_at)
    stmt = _apply_stats_username_filter(stmt, username=username)

    result = await session.execute(stmt)
    row = result.one()
    return OverviewResponse(
        total_cost_usd=float(row.total_cost_usd),
        actual_cost_usd=float(row.actual_cost_usd),
        request_count=int(row.request_count),
        total_token_usage=int(row.total_token_usage),
        date=_today_prefix(),
    )


@admin_router.get("/stats/usage", summary="按日期、用户名和模型统计用量")
async def stats_usage(
    session: AsyncSession = Depends(async_session_generator),
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    timezone: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    return await _list_usage_stats(
        session,
        timezone_name=timezone,
        start_at=start_at,
        end_at=end_at,
        username=username,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@admin_router.get("/stats/usage/export", summary="导出用量统计 CSV")
async def stats_usage_export(
    session: AsyncSession = Depends(async_session_generator),
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    timezone: str | None = None,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> Response:
    return await _export_usage_stats_csv(
        session,
        timezone_name=timezone,
        start_at=start_at,
        end_at=end_at,
        username=username,
        sort_by=sort_by,
        sort_order=sort_order,
        include_username=True,
    )


@admin_router.get("/stats/tokens", summary="Top 10 Token 用量")
async def stats_tokens(
    session: AsyncSession = Depends(async_session_generator),
) -> list[TokenStatsItem]:
    """返回今日费用 Top 10 的 Token（按 cost_usd 降序），含 Token 名称。"""
    today = _today_prefix()
    stmt = (
        select(
            UsageLog.token_id,
            UsageLog.username,
            Token.name.label("token_name"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost_usd"),
            func.count(UsageLog.id).label("request_count"),
        )
        .outerjoin(Token, UsageLog.token_id == Token.id)
        .where(UsageLog.created_at.like(f"{today}%"))
        .group_by(UsageLog.token_id, UsageLog.username, Token.name)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        TokenStatsItem(
            token_id=row.token_id,
            username=row.username,
            token_name=row.token_name,
            total_cost_usd=float(row.total_cost_usd),
            request_count=int(row.request_count),
        )
        for row in rows
    ]


@admin_router.get("/stats/models", summary="Top 10 模型请求量")
async def stats_models(
    session: AsyncSession = Depends(async_session_generator),
    start_at: str | None = None,
    end_at: str | None = None,
    username: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> dict:
    """返回按模型聚合的分页请求统计。"""
    return await _list_model_stats(
        session,
        start_at=start_at,
        end_at=end_at,
        username=username,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ---------------------------------------------------------------------------
# 用户管理路由（JWT 鉴权，需要 superadmin 角色）
# 使用独立 router 以避免与 admin_router 的 x-admin-key 依赖冲突
# ---------------------------------------------------------------------------

users_router = APIRouter(prefix="/admin", tags=["Admin: Users"])


class PromoteRequest(BaseModel):
    username: str
    role: str  # "admin" | "superadmin"


@users_router.get("/users", summary="列出所有管理员用户")
async def list_admin_users(
    session: AsyncSession = Depends(async_session_generator),
    _user: dict = Depends(require_role("superadmin")),
) -> list[AdminUser]:
    """查询 admin_users 表全部记录，按 created_at 升序返回。"""
    stmt = select(AdminUser).order_by(AdminUser.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@users_router.post("/users/promote", summary="提权 / 更新管理员角色")
async def promote_user(
    body: PromoteRequest,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_role("superadmin")),
) -> AdminUser:
    """将指定 LDAP 用户提权为 admin 或 superadmin。

    - 已在 admin_users 表中 → 更新 role。
    - 不在表中 → 插入新记录（created_by 为当前登录用户）。
    """
    if body.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=422, detail="role 必须为 'admin' 或 'superadmin'")

    stmt = select(AdminUser).where(AdminUser.username == body.username)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.role = body.role
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        logger.info(f"用户 [{body.username}] 角色更新为 [{body.role}]，操作者：{current_user['username']}")
        return existing
    else:
        new_user = AdminUser(
            username=body.username,
            role=body.role,
            created_by=current_user["username"],
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        logger.info(f"用户 [{body.username}] 已提权为 [{body.role}]，操作者：{current_user['username']}")
        return new_user


@users_router.delete("/users/{username}", summary="降权（删除管理员记录）")
async def demote_user(
    username: str,
    session: AsyncSession = Depends(async_session_generator),
    current_user: dict = Depends(require_role("superadmin")),
) -> dict:
    """从 admin_users 表删除指定用户（降权为普通用户）。

    - 不存在 → 404。
    - 存在 → 删除并返回 ``{"ok": true}``。
    """
    if username == current_user["username"]:
        raise HTTPException(status_code=400, detail="不能降权自己")

    stmt = select(AdminUser).where(AdminUser.username == username)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        raise HTTPException(status_code=404, detail=f"用户 [{username}] 不存在于 admin_users 表")

    await session.delete(existing)
    await session.commit()
    logger.info(f"用户 [{username}] 已从 admin_users 删除，操作者：{current_user['username']}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 分组-渠道管理路由
# ---------------------------------------------------------------------------

group_channel_router = APIRouter(
    prefix="/admin/groups",
    tags=["Admin: Group Channels"],
    dependencies=[Depends(require_admin_access)],
)


@group_channel_router.post("/{group_id}/channels/{channel_id}", summary="将渠道加入分组")
async def add_channel_to_group(
    group_id: str,
    channel_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    from db.models import GroupChannel, UserGroup, Channel
    # 验证分组和渠道存在
    if await session.get(UserGroup, group_id) is None:
        raise HTTPException(status_code=404, detail=f"分组 {group_id} 不存在")
    if await session.get(Channel, channel_id) is None:
        raise HTTPException(status_code=404, detail=f"渠道 {channel_id} 不存在")
    result = await session.execute(
        select(GroupChannel).where(
            GroupChannel.group_id == group_id,
            GroupChannel.channel_id == channel_id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(GroupChannel(group_id=group_id, channel_id=channel_id))
        await session.commit()
    return {"group_id": group_id, "channel_id": channel_id, "status": "ok"}


@group_channel_router.get("/{group_id}/channels", summary="列出分组下的所有渠道")
async def list_group_channels(
    group_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> list:
    from db.models import GroupChannel, Channel
    result = await session.execute(
        select(Channel)
        .join(GroupChannel, Channel.id == GroupChannel.channel_id)
        .where(GroupChannel.group_id == group_id)
    )
    channels = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "provider": c.provider,
            "base_url": c.base_url,
            "enabled": c.enabled,
            "weight": c.weight,
        }
        for c in channels
    ]


@group_channel_router.delete("/{group_id}/channels/{channel_id}", summary="从分组移除渠道")
async def remove_channel_from_group(
    group_id: str,
    channel_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    from db.models import GroupChannel
    result = await session.execute(
        select(GroupChannel).where(
            GroupChannel.group_id == group_id,
            GroupChannel.channel_id == channel_id,
        )
    )
    gc = result.scalar_one_or_none()
    if gc is None:
        raise HTTPException(status_code=404, detail="关联不存在")
    await session.delete(gc)
    await session.commit()
    return {"group_id": group_id, "channel_id": channel_id, "status": "removed"}


# ---------------------------------------------------------------------------
# 用户-分组管理路由
# ---------------------------------------------------------------------------

user_group_router = APIRouter(
    prefix="/admin/users-list",
    tags=["Admin: User Groups"],
    dependencies=[Depends(require_admin_access)],
)


@user_group_router.get("", summary="列出所有 AD 用户（懒加载记录）")
async def list_ad_users(
    session: AsyncSession = Depends(async_session_generator),
) -> list:
    from db.models import User
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [{"username": u.username, "created_at": u.created_at} for u in users]


@user_group_router.get("/{username}/groups", summary="获取用户所属分组")
async def get_user_groups_for_user(
    username: str,
    session: AsyncSession = Depends(async_session_generator),
) -> list:
    from services.auth_service import get_visible_groups
    groups = await get_visible_groups(username, session)
    return [
        {
            "id": g.id,
            "name": g.name,
            "priority": g.priority,
            "all_visible": g.all_visible,
        }
        for g in groups
    ]


@user_group_router.post("/{username}/groups/{group_id}", summary="将用户加入分组")
async def add_user_to_group(
    username: str,
    group_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    from db.models import User, UserGroupMembership, UserGroup
    # 验证分组存在
    if await session.get(UserGroup, group_id) is None:
        raise HTTPException(status_code=404, detail=f"分组 {group_id} 不存在")

    if await session.get(User, username) is None:
        session.add(User(username=username))

    result = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.username == username,
            UserGroupMembership.group_id == group_id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(UserGroupMembership(username=username, group_id=group_id))
    await session.commit()
    return {"username": username, "group_id": group_id, "status": "ok"}


@user_group_router.delete("/{username}/groups/{group_id}", summary="将用户从分组移除")
async def remove_user_from_group(
    username: str,
    group_id: str,
    session: AsyncSession = Depends(async_session_generator),
) -> dict:
    from db.models import UserGroupMembership
    result = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.username == username,
            UserGroupMembership.group_id == group_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="用户不在该分组中")
    await session.delete(membership)
    await session.commit()
    return {"username": username, "group_id": group_id, "status": "removed"}


rate_limit_router = crud_router(
    session=async_session_generator,
    model=RateLimit,
    create_schema=RateLimitCreate,
    update_schema=RateLimitUpdate,
    path="/admin/rate-limits",
    tags=["Rate Limits"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    deleted_methods=["read_multi"],
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)


@admin_router.get("/rate-limits", tags=["Rate Limits"], summary="获取分组限流规则列表")
async def list_rate_limits(
    group_id: str,
    session: AsyncSession = Depends(async_session_generator),
    _: None = Depends(require_admin_access),
) -> dict:
    crud = FastCRUD(RateLimit)
    result = await crud.get_multi(session, group_id=group_id)
    return result

model_price_router: APIRouter = crud_router(
    session=async_session_generator,
    model=ModelPrice,
    create_schema=ModelPriceCreate,
    update_schema=ModelPriceUpdate,
    path="/admin/model-prices",
    tags=["Admin: Model Prices"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

group_model_price_router: APIRouter = crud_router(
    session=async_session_generator,
    model=GroupModelPrice,
    create_schema=GroupModelPriceCreate,
    update_schema=GroupModelPriceUpdate,
    path="/admin/group-model-prices",
    tags=["Admin: Group Model Prices"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    read_multi_deps=_common_deps,
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)

voucher_router: APIRouter = crud_router(
    session=async_session_generator,
    model=Voucher,
    create_schema=VoucherCreate,
    update_schema=VoucherUpdate,
    path="/admin/vouchers",
    tags=["Admin: Vouchers"],
    create_deps=_common_deps,
    read_deps=_common_deps,
    deleted_methods=["create", "read_multi"],  # 手动实现：create 需返回 code，read_multi 按 created_at 倒序
    update_deps=_common_deps,
    delete_deps=_common_deps,
    db_delete_deps=_common_deps,
)


@voucher_router.post("/admin/vouchers", tags=["Admin: Vouchers"], summary="创建消费券", status_code=201)
async def create_voucher(
    body: VoucherCreate,
    session: AsyncSession = Depends(async_session_generator),
    _: None = Depends(require_admin_access),
) -> dict:
    """批量创建消费券，code 自动生成，count=1 时返回单条记录，count>1 时返回 list。"""
    count = max(1, body.count)
    voucher_data = body.model_dump(exclude={"count"})
    vouchers = [Voucher(**voucher_data) for _ in range(count)]
    for v in vouchers:
        session.add(v)
    await session.commit()
    for v in vouchers:
        await session.refresh(v)
    if count == 1:
        return vouchers[0].model_dump()
    return {"count": count, "vouchers": [v.model_dump() for v in vouchers]}


@voucher_router.get("/admin/vouchers", tags=["Admin: Vouchers"], summary="列出消费券（按创建时间倒序）")
async def list_vouchers(
    session: AsyncSession = Depends(async_session_generator),
    _: None = Depends(require_admin_access),
    page: int = 1,
    items_per_page: int = 100,
) -> dict:
    """列出所有消费券，按创建时间降序排列（最新的在前）。"""
    offset = (page - 1) * items_per_page
    stmt = select(Voucher).order_by(Voucher.created_at.desc()).offset(offset).limit(items_per_page)
    result = await session.execute(stmt)
    vouchers = list(result.scalars().all())
    count_result = await session.execute(select(func.count()).select_from(Voucher))
    total = count_result.scalar() or 0
    return {
        "data": [v.model_dump() for v in vouchers],
        "total": total,
        "has_more": offset + len(vouchers) < total,
        "page": page,
        "items_per_page": items_per_page,
    }
