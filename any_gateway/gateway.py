from fastapi.responses import Response, JSONResponse, StreamingResponse, FileResponse
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from constants import (
    GATEWAY_PORT,
    MAX_QUEUE_SIZE,
    CONFIG_FILE,
    TIMEOUT_BOUND,
    NUM_LOG_CONSUMERS,
    SKIP_SSL_VERIFY,
)
from loguru import logger
from urllib.parse import urljoin
from middleware.auth import AuthMiddleware
from db.database import init_db, engine
from db.models import Channel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from services.quota import check_quota, update_usage, update_user_balance
from services.pricing import calculate_cost
from services.responses_converter import (
    responses_to_chat_request,
    chat_resp_to_responses_resp,
    format_responses_sse,
    _ResponsesStreamState,
)
from services.auth_service import require_auth, optional_require_auth
from admin.router import token_router, channel_router, group_router, admin_router, auth_router, me_router, users_router, user_router, group_channel_router, user_group_router, rate_limit_router, model_price_router, group_model_price_router, voucher_router
import yaml
import json
import time
import asyncio
import random
import httpx
import log_writer
import dataclasses
from uuid import uuid4


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 启动和关闭时的初始化/清理"""
    # 启动时初始化
    logger.info("正在启动应用...")

    # 初始化数据库
    await init_db()
    logger.info("数据库初始化完成")

    # 初始化超级管理员（若 SUPERADMIN_USERNAME 已配置）
    from services.auth_service import init_superadmin
    from db.database import engine
    from sqlalchemy.ext.asyncio import AsyncSession
    try:
        async with AsyncSession(engine) as session:
            await init_superadmin(session)
        logger.info("超级管理员初始化检查完成")
    except Exception as _e:
        logger.error(f"超级管理员初始化失败，应用继续启动: {_e}")

    # 初始化日志队列
    log_writer.log_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    logger.info("日志队列已初始化")

    logger.info(f"SKIP_SSL_VERIFY={SKIP_SSL_VERIFY}（跳过上游 SSL 证书验证）")

    # 启动多个后台日志消费者任务
    consumer_tasks = []
    for i in range(NUM_LOG_CONSUMERS):
        task = asyncio.create_task(log_writer.log_consumer())
        consumer_tasks.append(task)
        logger.info(f"日志消费者任务 {i+1}/{NUM_LOG_CONSUMERS} 已启动")

    # 保存所有日志任务的引用,防止被垃圾回收
    app.state.log_tasks = set()
    app.state.consumer_tasks = consumer_tasks  # 保存消费者任务引用

    try:
        yield  # 应用运行中
    finally:
        # 关闭时清理资源
        logger.info("正在关闭应用...")

        # 等待所有日志入队任务完成
        if app.state.log_tasks:
            logger.info(f"等待 {len(app.state.log_tasks)} 个日志任务完成...")
            done, pending = await asyncio.wait(app.state.log_tasks, timeout=5.0)
            if pending:
                logger.warning(f"仍有 {len(pending)} 个日志任务未完成,强制取消")
                for task in pending:
                    task.cancel()

        if log_writer.log_queue is not None:
            try:
                # 等待队列中的所有任务处理完成
                await asyncio.wait_for(log_writer.log_queue.join(), timeout=5.0)
                logger.info("队列中的所有日志已处理完成")

                # 向每个消费者发送关闭信号
                logger.info(f"正在发送关闭信号到 {len(consumer_tasks)} 个消费者...")
                for i in range(len(consumer_tasks)):
                    await asyncio.wait_for(log_writer.log_queue.put(None), timeout=1.0)

                # 等待所有消费者任务完成
                done, pending = await asyncio.wait(consumer_tasks, timeout=5.0)
                logger.info(f"{len(done)}/{len(consumer_tasks)} 个消费者已正常退出")

                if pending:
                    logger.warning(f"仍有 {len(pending)} 个消费者未退出,强制取消")
                    for task in pending:
                        task.cancel()
                    try:
                        await asyncio.wait(pending, timeout=2.0)
                    except Exception:
                        pass

            except asyncio.TimeoutError:
                logger.warning("日志消费者关闭超时,强制取消所有任务")
                for task in consumer_tasks:
                    task.cancel()
                try:
                    await asyncio.gather(*consumer_tasks, return_exceptions=True)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"关闭日志消费者时出错: {e}")
                for task in consumer_tasks:
                    task.cancel()

        logger.info("应用已关闭")


app = FastAPI(title="Micro Gateway", lifespan=lifespan)
# 注意：add_middleware 顺序为 LIFO，AuthMiddleware 最后 add 则最先执行。
# 未来若增加 CORSMiddleware，需在此行之前 add（使其在 Auth 之后执行）。
app.add_middleware(AuthMiddleware)

# Admin 路由：FastCRUD 自动生成的 CRUD + 手动业务路由
# verify_admin_key 依赖已在 *_deps 参数中注入，无需重复添加。
# auth_router 无需 admin key（登录端点本身即鉴权入口）。
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(user_router)
app.include_router(token_router)
app.include_router(channel_router)
app.include_router(group_router)
app.include_router(admin_router)
app.include_router(users_router)
app.include_router(group_channel_router)
app.include_router(user_group_router)
app.include_router(rate_limit_router)
app.include_router(model_price_router)
app.include_router(group_model_price_router)
app.include_router(voucher_router)


@app.get("/public/model-prices", tags=["Public"])
async def public_model_prices():
    """公开的模型价格列表，无需认证"""
    from db.database import engine
    from db.models import ModelPrice
    async with AsyncSession(engine, expire_on_commit=False) as session:
        result = await session.execute(select(ModelPrice))
        rows = result.scalars().all()
        return {
            "data": [
                {
                    "model_name": r.model_name,
                    "unit": r.unit,
                    "price_per_unit": r.price_per_unit,
                    "context_length": r.context_length,
                    "vendor": r.vendor,
                    "stability": r.stability,
                }
                for r in rows
            ]
        }


def load_config() -> Dict[str, Any]:
    """从 YAML 文件加载配置"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    return {}


def save_config(config_data: Dict[str, Any]) -> bool:
    """保存配置到 YAML 文件"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, allow_unicode=True, default_flow_style=False)
        logger.info("配置文件已保存")
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


config = load_config()


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def get_model_info(group_data, model_name):
    models = group_data.get("models", [])
    for model in models:
        model_id = model.get("id") or model.get("name")
        if model_id == model_name:
            return {
                "base_url": group_data.get("base_url"),
                "api_key": group_data.get("api_key"),
                "model": model_name,
            }
    return {
        "base_url": group_data.get("base_url"),
        "api_key": group_data.get("api_key"),
    }


async def find_backend_for_model(
    model_name: str,
    username: str | None = None,
    group_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    根据模型名称查找后端渠道。

    路由策略：
    1. 若 group_id 不为空，直接在该分组的渠道中按 weight 加权随机选取，跳过用户组查找。
    2. 若 username 不为空，按用户所属分组的 priority 降序查找，
       在第一个支持该模型的分组内按 weight 加权随机选渠道。
    3. 其余情况，回退到旧逻辑：_admin_fallback / superadmin 遍历所有 enabled 渠道。
    """
    from db.models import UserGroup, GroupChannel

    def _extract_model_info(channel: Channel, req_model: str) -> Optional[Dict[str, Any]]:
        """从 Channel 对象提取模型路由信息，不支持时返回 None。"""
        channel_models: list = []
        if channel.models:
            try:
                parsed = json.loads(channel.models)
                if isinstance(parsed, list):
                    channel_models = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        model_mapping: dict = {}
        if channel.model_mapping:
            try:
                parsed = json.loads(channel.model_mapping)
                if isinstance(parsed, dict):
                    model_mapping = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        model_ids = []
        for m in channel_models:
            if isinstance(m, str):
                model_ids.append(m.removeprefix("models/"))
            elif isinstance(m, dict):
                raw = m.get("id") or m.get("name") or ""
                model_ids.append(raw.removeprefix("models/"))

        all_supported = set(model_ids) | set(model_mapping.keys())
        if req_model not in all_supported:
            return None

        upstream_model = model_mapping.get(req_model, req_model)
        return {
            "base_url": channel.base_url,
            "api_key": channel.api_key,
            "model": upstream_model,
            "provider": channel.provider or "",
            "proxy_url": channel.proxy_url,
            "disable_ssl": bool(channel.disable_ssl),
            "disable_compression": bool(channel.disable_compression),
        }

    def _weighted_choice(channels: list) -> Optional[Channel]:
        """按 weight 加权随机选取渠道。"""
        total = sum(c.weight for c in channels)
        if total <= 0:
            return channels[0] if channels else None
        r = random.uniform(0, total)
        cumulative = 0.0
        for c in channels:
            cumulative += c.weight
            if r <= cumulative:
                return c
        return channels[-1]

    def _pick(supported: list) -> Optional[Dict[str, Any]]:
        """从候选渠道列表中加权随机选取，返回路由信息。"""
        chosen = _weighted_choice(supported)
        return _extract_model_info(chosen, model_name)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # 策略 1：token 绑定了特定分组，直接路由
        if group_id:
            stmt = (
                select(Channel)
                .join(GroupChannel, Channel.id == GroupChannel.channel_id)
                .where(
                    GroupChannel.group_id == group_id,
                    Channel.enabled == True,
                )
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()
            supported = [c for c in candidates if _extract_model_info(c, model_name)]
            return _pick(supported) if supported else None

        if not username:
            return None  # 匿名 token 不允许访问

        # 1. 获取用户可见分组（显式 membership + all_visible 分组），按 priority 降序
        from services.auth_service import get_visible_groups
        groups = await get_visible_groups(username, session)

        for group in groups:
            # 2. 获取该分组下所有 enabled 渠道
            stmt = (
                select(Channel)
                .join(GroupChannel, Channel.id == GroupChannel.channel_id)
                .where(
                    GroupChannel.group_id == group.id,
                    Channel.enabled == True,
                )
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            # 3. 过滤支持该模型的渠道，加权随机选取
            supported = [c for c in candidates if _extract_model_info(c, model_name)]
            if supported:
                return _pick(supported)

        # 分组内未找到，仅 _admin_fallback 或 superadmin 允许回退到全局渠道
        if username != "_admin_fallback":
            from db.models import AdminUser
            admin_result = await session.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            admin_user = admin_result.scalar_one_or_none()
            if not (admin_user and admin_user.role == "superadmin"):
                return None

        # _admin_fallback / superadmin：遍历所有 enabled 渠道
        result = await session.execute(
            select(Channel).where(Channel.enabled == True)
        )
        channels = result.scalars().all()
        for channel in channels:
            info = _extract_model_info(channel, model_name)
            if info:
                return info
        return None


async def _get_group_multiplier(group_id: str | None) -> float:
    """查询 group.multiplier，找不到返回 1.0。"""
    if not group_id:
        return 1.0
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            from fastcrud import FastCRUD
            from db.models import UserGroup
            group = await FastCRUD(UserGroup).get(session, id=group_id)
            return group.get("multiplier", 1.0) if group else 1.0
    except Exception:
        return 1.0


async def _maybe_deduct(covered: bool, username: str | None, cost_usd: float) -> None:
    """根据 covered_by_package 决定是否扣减用户余额。covered=True 时跳过扣费。"""
    if covered:
        return
    import services.quota as _quota_mod
    await _quota_mod.update_user_balance(username, cost_usd)


async def _finalize_stream_usage(
    request: Request,
    request_id: str,
    model_name: str | None,
    duration_ms: float,
    response_status: int,
    accumulated_chunks: list[str],
    provider: str,
) -> None:
    """在后台完成流式用量计算与落库，避免在已取消的请求上下文中操作 DB。"""
    try:
        stream_usage = parse_stream_usage(accumulated_chunks, provider)
        stream_input_tokens = stream_usage.input_tokens
        stream_output_tokens = stream_usage.output_tokens
        stream_cache_read_tokens = stream_usage.cache_read_tokens
        stream_cache_creation_tokens = stream_usage.cache_creation_tokens
        logger.debug(
            f"流式用量解析完成: provider={provider!r} input={stream_input_tokens} "
            f"output={stream_output_tokens} cache_read={stream_cache_read_tokens} "
            f"cache_creation={stream_cache_creation_tokens}"
        )

        stream_group_id = getattr(request.state, "token_group_id", None)
        stream_multiplier = await _get_group_multiplier(stream_group_id)
        async with AsyncSession(engine, expire_on_commit=False) as pricing_session:
            stream_cost_usd = await calculate_cost(
                session=pricing_session,
                group_id=stream_group_id,
                model=model_name,
                input_tokens=stream_input_tokens,
                output_tokens=stream_output_tokens,
                cache_read_tokens=stream_cache_read_tokens,
                cache_creation_tokens=stream_cache_creation_tokens,
                multiplier=stream_multiplier,
            )

        await update_usage(
            token_id=getattr(request.state, "token_id", None),
            channel_id=None,
            model=model_name,
            input_tokens=stream_input_tokens,
            output_tokens=stream_output_tokens,
            cost_usd=stream_cost_usd,
            duration_ms=duration_ms,
            status=response_status or None,
            is_stream=True,
            username=getattr(request.state, "token_username", None),
            request_id=request_id,
            cache_read_tokens=stream_cache_read_tokens,
            cache_creation_tokens=stream_cache_creation_tokens,
            covered_by_package=getattr(request.state, "covered_by_package", False),
        )

        if stream_group_id:
            await _update_rate_limit_counters(
                group_id=stream_group_id,
                request_id=request_id,
                input_tokens=stream_input_tokens,
                output_tokens=stream_output_tokens,
                cost_usd=stream_cost_usd,
                username=getattr(request.state, "token_username", None),
            )

        await _maybe_deduct(
            covered=getattr(request.state, "covered_by_package", False),
            username=getattr(request.state, "token_username", None),
            cost_usd=stream_cost_usd,
        )
    except Exception:
        logger.exception(f"流式请求收尾失败 (request_id={request_id})")


async def _update_rate_limit_counters(
    group_id: str,
    request_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    username: str | None = None,
) -> None:
    """响应后更新 Redis 限流计数（fire-and-forget）。username 存在时使用 per-user key。"""
    try:
        from middleware.auth import _get_redis
        from services.rate_limit_redis import build_key, record_request, record_value
        from fastcrud import FastCRUD
        from db.models import RateLimit
        from sqlalchemy.ext.asyncio import AsyncSession

        redis_client = await _get_redis()
        async with AsyncSession(engine) as session:
            crud = FastCRUD(RateLimit)
            result = await crud.get_multi(session, group_id=group_id)
            for rule in result.get("data", []):
                if rule["value"] <= 0:
                    continue
                key = build_key(group_id, rule["limit_type"], rule["window_sec"], username)
                if rule["limit_type"] == "request_limit":
                    await record_request(redis_client, key, rule["window_sec"], request_id)
                elif rule["limit_type"] == "token_limit":
                    await record_value(redis_client, key, rule["window_sec"], request_id, input_tokens + output_tokens)
                elif rule["limit_type"] == "quota_limit":
                    await record_value(redis_client, key, rule["window_sec"], request_id, cost_usd)
    except Exception:
        logger.exception(f"Redis 限流计数更新失败 (group_id={group_id})")


@dataclasses.dataclass
class StreamUsage:
    """流式响应 token 用量，支持三种协议的 cache 字段。"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0    # Anthropic: cache_read_input_tokens / OpenAI: cached_tokens / Gemini: cachedContentTokenCount
    cache_creation_tokens: int = 0  # Anthropic: cache_creation_input_tokens（OpenAI/Gemini 无此字段，留 0）


def inject_stream_options(body: dict, provider: str) -> None:
    """
    OpenAI 协议流式请求需要注入 stream_options.include_usage=true，
    才能在流中获取 token 用量数据。Anthropic/Gemini 不需要。
    就地修改 body dict，不返回值。
    """
    if provider.lower() not in ("anthropic", "gemini"):
        body.setdefault("stream_options", {})["include_usage"] = True


def _safe_int(value: object, default: int = 0) -> int:
    """安全转换为 int，转换失败时返回 default。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_stream_usage(chunks: list[str], provider: str) -> StreamUsage:
    """
    从累积的 SSE chunks 中解析 input/output token 用量。

    协议差异：
    - openai:    最后一个含非 null usage 的 data chunk，字段 prompt_tokens / completion_tokens
    - anthropic: message_start 事件取 input_tokens，message_delta 事件取 output_tokens
    - gemini:    最后一个含 usageMetadata 的 data chunk，字段 promptTokenCount / candidatesTokenCount
    - 其他/空:   降级为 openai 格式，找不到则返回 StreamUsage()

    :param chunks: forward_streaming_request 中累积的原始 SSE 行列表
    :param provider: 渠道 provider 字符串（来自 Channel.provider）
    :return: StreamUsage dataclass
    """
    p = (provider or "").lower()

    if p == "anthropic":
        return _parse_anthropic_usage(chunks)
    elif p == "gemini":
        return _parse_gemini_usage(chunks)
    else:
        result = _parse_openai_usage(chunks)
        # 零用量可能是真实值或解析失败（provider 未知时无法区分），此 warning 仅供排查配置问题
        if result.input_tokens == 0 and result.output_tokens == 0 and p not in ("openai", ""):
            logger.warning(f"parse_stream_usage: provider={provider!r} 未匹配已知协议，已降级为 OpenAI 格式，用量可能为 0")
        return result


def _parse_openai_usage(chunks: list[str]) -> StreamUsage:
    """扫描所有 data 行，取最后一个含非 null usage 的 JSON。"""
    result = StreamUsage()
    for line in chunks:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            continue
        usage = obj.get("usage")
        if usage and isinstance(usage, dict):
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            if pt is not None and ct is not None:
                result.input_tokens = _safe_int(pt)
                result.output_tokens = _safe_int(ct)
                # OpenAI prompt caching: usage.prompt_tokens_details.cached_tokens
                details = usage.get("prompt_tokens_details")
                if details and isinstance(details, dict):
                    result.cache_read_tokens = _safe_int(details.get("cached_tokens", 0))
    return result


def _parse_anthropic_usage(chunks: list[str]) -> StreamUsage:
    """
    状态机解析 Anthropic SSE：
    - event: message_start → 取 message.usage.input_tokens /
                              cache_read_input_tokens / cache_creation_input_tokens
    - event: message_delta → 取 usage.output_tokens
    """
    result = StreamUsage()
    pending_event = None
    for line in chunks:
        stripped = line.strip()
        if stripped.startswith("event:"):
            pending_event = stripped[6:].strip()
            continue
        if stripped.startswith("data:") and pending_event:
            payload = stripped[5:].strip()
            try:
                obj = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                pending_event = None
                continue
            if pending_event == "message_start":
                usage = obj.get("message", {}).get("usage", {})
                result.input_tokens = _safe_int(usage.get("input_tokens", 0))
                result.cache_read_tokens = _safe_int(usage.get("cache_read_input_tokens", 0))
                result.cache_creation_tokens = _safe_int(usage.get("cache_creation_input_tokens", 0))
            elif pending_event == "message_delta":
                usage = obj.get("usage", {})
                result.output_tokens = _safe_int(usage.get("output_tokens", 0))
            pending_event = None
    return result


def _parse_gemini_usage(chunks: list[str]) -> StreamUsage:
    """扫描所有 data 行，取最后一个含 usageMetadata 的 JSON。"""
    result = StreamUsage()
    for line in chunks:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[5:].strip()
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            continue
        meta = obj.get("usageMetadata")
        if meta and isinstance(meta, dict):
            result.input_tokens = _safe_int(meta.get("promptTokenCount", 0))
            result.output_tokens = _safe_int(meta.get("candidatesTokenCount", 0))
            result.cache_read_tokens = _safe_int(meta.get("cachedContentTokenCount", 0))
    return result


def _httpx_client_kwargs(
    timeout, *, disable_ssl: bool = False, proxy_url: Optional[str] = None
) -> dict:
    """统一构造 httpx.AsyncClient 关键字参数：渠道级 disable_ssl 与全局 SKIP_SSL_VERIFY 取或，proxy_url 非空时启用代理。"""
    kwargs: dict = {"timeout": timeout, "verify": not (SKIP_SSL_VERIFY or disable_ssl)}
    if proxy_url:
        kwargs["proxy"] = proxy_url
    return kwargs


def _apply_accept_encoding(headers: dict, disable_compression: bool) -> None:
    """渠道级压缩控制：disable_compression 时强制 identity（兼容压缩却不回传 Content-Encoding 的上游）；否则交给 httpx 自行协商（合规上游会回传 Content-Encoding，可正常解压）。"""
    if disable_compression:
        headers["accept-encoding"] = "identity"
    else:
        headers.pop("accept-encoding", None)


async def forward_streaming_request(
    request: Request,
    path: str,
    url: str,
    headers: dict,
    body: bytes,
    backend_url: str,
    model_name: Optional[str],
    start_time: float,
    request_id: str,
    provider: str = "",
    *,
    proxy_url: Optional[str] = None,
    disable_ssl: bool = False,
    disable_compression: bool = False,
) -> StreamingResponse:
    """
    转发流式请求到后端服务并返回 SSE 流式响应。
    累积所有响应内容用于日志记录。
    """
    # 用于累积所有响应内容（用于日志）
    accumulated_chunks = []
    response_status = 0
    response_headers = {}
    error_message = None

    async def stream_generator():
        nonlocal response_status, response_headers, error_message

        try:
            async with httpx.AsyncClient(
                **_httpx_client_kwargs(TIMEOUT_BOUND, disable_ssl=disable_ssl, proxy_url=proxy_url)
            ) as client:
                async with client.stream(
                    method=request.method,
                    url=url,
                    content=body if body else None,
                    headers=headers,
                    follow_redirects=True,
                ) as response:
                    # 记录响应状态和头部
                    response_status = response.status_code
                    response_headers = dict(response.headers)
                    response_headers.pop("content-encoding", None)
                    response_headers.pop("content-length", None)

                    logger.info(
                        f"Streaming response started: status={response_status}, content-type={response_headers.get('content-type')}"
                    )

                    # 上游返回 4xx/5xx：读取错误体并包装为 SSE error 事件
                    if response_status >= 400:
                        error_body_parts: list[str] = []
                        async for line in response.aiter_lines():
                            error_body_parts.append(line)
                        error_body = "\n".join(error_body_parts)
                        accumulated_chunks.append(error_body)

                        try:
                            error_json = json.loads(error_body)
                            # 标准化为 {"error": {"message": ..., "code": ...}}
                            if "error" not in error_json:
                                error_json = {"error": {"message": str(error_json), "code": response_status}}
                            elif isinstance(error_json["error"], str):
                                error_json = {"error": {"message": error_json["error"], "code": response_status}}
                        except Exception:
                            # 非 JSON 响应（如 nginx HTML 502 页面）：只传状态码，不传原始 HTML
                            error_json = {"error": {"message": f"上游服务异常 (HTTP {response_status})", "code": response_status}}

                        error_message = error_json["error"].get("message", "") if isinstance(error_json.get("error"), dict) else str(error_json.get("error"))
                        logger.warning(f"Streaming upstream error {response_status}: {error_message}")
                        error_chunk = f"data: {json.dumps(error_json, ensure_ascii=False)}\n\n"
                        accumulated_chunks.append(error_chunk)
                        yield error_chunk.encode("utf-8")
                    else:
                        # 逐行读取并转发
                        async for line in response.aiter_lines():
                            chunk_data = line + "\n"
                            accumulated_chunks.append(chunk_data)
                            yield chunk_data.encode("utf-8")

                        logger.info(
                            f"Streaming completed: {len(accumulated_chunks)} chunks received"
                        )

        except httpx.RequestError as e:
            error_message = f"Request error: {str(e)}"
            logger.error(f"Streaming error: {error_message}")
            error_chunk = f"data: {json.dumps({'error': {'message': error_message, 'code': 0}})}\n\n"
            accumulated_chunks.append(error_chunk)
            yield error_chunk.encode("utf-8")

        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Streaming error: {error_message}")
            error_chunk = f"data: {json.dumps({'error': {'message': error_message, 'code': 0}})}\n\n"
            accumulated_chunks.append(error_chunk)
            yield error_chunk.encode("utf-8")

        finally:
            # 流结束后记录日志
            duration_ms = (time.time() - start_time) * 1000

            task = asyncio.create_task(
                log_writer.enqueue_log(
                    {
                        "timestamp": timestamp(),
                        "method": request.method,
                        "path": path,
                        "request_url": url,
                        "request_headers": headers,
                        "request_body": (
                            body.decode("utf-8", errors="replace") if body else ""
                        ),
                        "response_status": response_status,
                        "response_headers": response_headers,
                        "response_body": "".join(accumulated_chunks),
                        "duration_ms": duration_ms,
                        "model_name": model_name,
                        "backend_url": backend_url,
                        "is_stream": True,
                        "error": error_message,
                        "token_id": getattr(request.state, "token_id", None),
                        "request_id": request_id,
                    }
                )
            )
            app.state.log_tasks.add(task)
            task.add_done_callback(app.state.log_tasks.discard)
            logger.info(f"流式请求日志已入队, 当前task数量: {len(app.state.log_tasks)}")

            finalize_task = asyncio.create_task(
                _finalize_stream_usage(
                    request=request,
                    request_id=request_id,
                    model_name=model_name,
                    duration_ms=duration_ms,
                    response_status=response_status,
                    accumulated_chunks=accumulated_chunks,
                    provider=provider,
                )
            )
            app.state.log_tasks.add(finalize_task)
            finalize_task.add_done_callback(app.state.log_tasks.discard)

    # 返回流式响应
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def forward_request(
    request: Request, path: str, backend_url: str, api_key: Optional[str] = None, provider: str = "",
    *, proxy_url: Optional[str] = None, disable_ssl: bool = False, disable_compression: bool = False,
) -> Response:
    """
    转发请求到后端服务并返回响应。
    如果提供了 api_key，透明替换客户端原始认证头的 value，保留 header key 不变。
    支持自动检测并转发流式响应（SSE）。
    """

    start_time = time.time()
    request_id = uuid4().hex

    # 构建完整的后端 URL
    url = urljoin(backend_url.rstrip("/") + "/", path.lstrip("/"))

    # 保留查询参数
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # 读取请求体
    body = await request.body()

    # 准备请求头（排除 host 等代理相关的头）
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    # 渠道级压缩控制：作为反向代理，网关需读取/解析响应体（SSE 计费）。
    # 部分上游（如 APISIX）在 Accept-Encoding 含 br/zstd 时会压缩响应却不回传
    # Content-Encoding 头，导致 httpx 无法自动解压、响应流乱码且无法计费——
    # 对这类渠道在配置中开启 disable_compression 即强制 identity。
    _apply_accept_encoding(headers, disable_compression)

    # 透明代理：保留客户端原始认证头的 key，仅替换 value 为渠道配置的 api_key
    if api_key:
        if "authorization" in headers:
            headers["authorization"] = f"Bearer {api_key}"
        if "x-api-key" in headers:
            headers["x-api-key"] = api_key
        if "x-goog-api-key" in headers:
            headers["x-goog-api-key"] = api_key

    logger.info(f"Request body: {body[:200] if body else ''}")
    logger.info(f"Request headers: {headers}")
    logger.info(f"Request URL: {url}")
    logger.info(f"Forwarding {request.method} request to {url}")

    # 提取模型名称和检查是否为流式请求
    model_name = None
    is_stream_request = False
    body_json_parsed: Optional[dict] = None
    try:
        if body:
            body_json_parsed = json.loads(body)
            model_name = body_json_parsed.get("model")
            is_stream_request = body_json_parsed.get("stream", False)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    # 如果请求要求流式，使用流式转发
    if is_stream_request:
        logger.info("检测到流式请求，使用 SSE 转发")
        # OpenAI 协议需要注入 stream_options.include_usage=true，
        # 否则上游不会在流中返回 usage 数据
        if body_json_parsed is not None and provider.lower() not in ("anthropic", "gemini"):
            inject_stream_options(body_json_parsed, provider)
            body = json.dumps(body_json_parsed).encode("utf-8")
            logger.debug(f"已注入 stream_options.include_usage=true (provider={provider!r})")
        return await forward_streaming_request(
            request, path, url, headers, body, backend_url, model_name, start_time,
            request_id, provider,
            proxy_url=proxy_url, disable_ssl=disable_ssl, disable_compression=disable_compression,
        )

    try:
        async with httpx.AsyncClient(
            **_httpx_client_kwargs(TIMEOUT_BOUND, disable_ssl=disable_ssl, proxy_url=proxy_url)
        ) as client:
            # 转发请求到后端
            response = await client.request(
                method=request.method,
                url=url,
                content=body if body else None,
                headers=headers,
                follow_redirects=True,
            )

            # 读取响应内容
            response_content = response.content

            # 准备响应头（移除压缩相关的头，因为 httpx 已自动解压）
            response_headers = dict(response.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-length", None)

            # 计算耗时
            duration_ms = (time.time() - start_time) * 1000

            # 解码响应体用于日志 (失败时使用 replace 策略)
            response_body_log = response_content.decode("utf-8", errors="replace")

            # 从响应体中提取 token 用量（支持 OpenAI、Anthropic、Gemini 格式）
            input_tokens = 0
            output_tokens = 0
            cache_read_tokens = 0
            cache_creation_tokens = 0
            try:
                resp_json = json.loads(response_content)
                usage = resp_json.get("usage") or {}
                usage_meta = resp_json.get("usageMetadata") or {}  # Gemini native
                prompt_details = usage.get("prompt_tokens_details") or {}

                # input / output
                input_tokens = _safe_int(
                    usage.get("input_tokens")       # Anthropic
                    or usage.get("prompt_tokens")   # OpenAI
                    or usage_meta.get("promptTokenCount")  # Gemini native
                    or 0
                )
                output_tokens = _safe_int(
                    usage.get("output_tokens")          # Anthropic
                    or usage.get("completion_tokens")   # OpenAI
                    or usage_meta.get("candidatesTokenCount")  # Gemini native
                    or 0
                )

                # cache tokens（三种协议字段不同）
                cache_read_tokens = _safe_int(
                    usage.get("cache_read_input_tokens")              # Anthropic（独立）
                    or prompt_details.get("cached_tokens")            # OpenAI（子集）
                    or usage_meta.get("cachedContentTokenCount")      # Gemini（子集）
                    or 0
                )
                cache_creation_tokens = _safe_int(
                    usage.get("cache_creation_input_tokens") or 0     # Anthropic only
                )
            except Exception:
                pass  # 解析失败时保持 0

            # 异步记录日志 - 保存任务引用防止被GC回收
            task = asyncio.create_task(
                log_writer.enqueue_log(
                    {
                        "timestamp": timestamp(),
                        "method": request.method,
                        "path": path,
                        "request_url": url,
                        "request_headers": dict(headers),
                        "request_body": (
                            body.decode("utf-8", errors="replace") if body else ""
                        ),
                        "response_status": response.status_code,
                        "response_headers": response_headers,
                        "response_body": response_body_log,
                        "duration_ms": duration_ms,
                        "model_name": model_name,
                        "backend_url": backend_url,
                        "token_id": getattr(request.state, "token_id", None),
                        "request_id": request_id,
                    }
                )
            )
            app.state.log_tasks.add(task)
            task.add_done_callback(app.state.log_tasks.discard)
            logger.info(f"当前task数量: {len(app.state.log_tasks)}")

            # fire-and-forget 更新用量（不阻塞响应）
            _group_id = getattr(request.state, "token_group_id", None)
            _multiplier = await _get_group_multiplier(_group_id)
            async with AsyncSession(engine, expire_on_commit=False) as _ps:
                _cost_usd = await calculate_cost(
                    session=_ps,
                    group_id=_group_id,
                    model=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                    multiplier=_multiplier,
                )
            usage_task = asyncio.create_task(
                update_usage(
                    token_id=getattr(request.state, "token_id", None),
                    channel_id=None,
                    model=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=_cost_usd,
                    duration_ms=duration_ms,
                    status=response.status_code,
                    is_stream=False,
                    username=getattr(request.state, "token_username", None),
                    request_id=request_id,
                    cache_read_tokens=cache_read_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                    covered_by_package=getattr(request.state, "covered_by_package", False),
                )
            )
            request.app.state.log_tasks.add(usage_task)
            usage_task.add_done_callback(request.app.state.log_tasks.discard)

            # After 阶段：更新 Redis 限流计数（fire-and-forget）
            if _group_id:
                asyncio.create_task(_update_rate_limit_counters(
                    group_id=_group_id,
                    request_id=request_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=_cost_usd,
                    username=getattr(request.state, "token_username", None),
                ))

            # After 阶段：扣减用户余额（fire-and-forget）
            asyncio.create_task(_maybe_deduct(
                covered=getattr(request.state, "covered_by_package", False),
                username=getattr(request.state, "token_username", None),
                cost_usd=_cost_usd,
            ))

            # 直接返回后端的响应状态码和内容
            return Response(
                content=response_content,
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get("content-type"),
            )

    except httpx.RequestError as e:
        # 网络错误、连接错误等直接抛出
        logger.error(f"Request error while forwarding to {url}: {str(e)}")

        # 记录错误日志
        duration_ms = (time.time() - start_time) * 1000
        task = asyncio.create_task(
            log_writer.enqueue_log(
                {
                    "timestamp": timestamp(),
                    "method": request.method,
                    "path": path,
                    "request_url": url,
                    "request_headers": dict(headers),
                    "request_body": body.decode("utf-8") if body else "",
                    "response_status": 0,
                    "response_headers": {},
                    "response_body": f"Error: {str(e)}",
                    "duration_ms": duration_ms,
                    "model_name": model_name,
                    "backend_url": backend_url,
                    "token_id": getattr(request.state, "token_id", None),
                    "request_id": request_id,
                }
            )
        )
        app.state.log_tasks.add(task)
        task.add_done_callback(app.state.log_tasks.discard)
        logger.info(f"当前task数量: {len(app.state.log_tasks)}")

        raise
    except Exception as e:
        # 其他异常直接抛出
        logger.error(f"Unexpected error while forwarding to {url}: {str(e)}")

        # 记录错误日志
        duration_ms = (time.time() - start_time) * 1000
        task = asyncio.create_task(
            log_writer.enqueue_log(
                {
                    "timestamp": timestamp(),
                    "method": request.method,
                    "path": path,
                    "request_url": url,
                    "request_headers": dict(headers),
                    "request_body": body.decode("utf-8") if body else "",
                    "response_status": 0,
                    "response_headers": {},
                    "response_body": f"Error: {str(e)}",
                    "duration_ms": duration_ms,
                    "model_name": model_name,
                    "backend_url": backend_url,
                    "token_id": getattr(request.state, "token_id", None),
                    "request_id": request_id,
                }
            )
        )
        app.state.log_tasks.add(task)
        task.add_done_callback(app.state.log_tasks.discard)
        logger.info(f"当前task数量: {len(app.state.log_tasks)}")

        raise


# 模型列表 API
@app.get("/v1/models")
async def list_models(
    request: Request,
    current_user: Optional[dict] = Depends(optional_require_auth),
):
    """
    返回可用模型列表（OpenAI 格式）。

    认证优先级：
    1. API Key（由 middleware 注入 request.state.token_group_id / token_username）
       - token_group_id 有值 → 只返回该 group 的模型
       - token_username 有值（无 group 绑定）→ 返回该用户所在所有分组的模型
    2. JWT → 原有逻辑（admin/superadmin 看全部，普通用户看所在分组）
    3. 两者都无 → 401
    """
    from db.models import Channel, GroupChannel

    # 从 middleware 注入的 API Key token 信息
    token_group_id: str | None = getattr(request.state, "token_group_id", None)
    token_username: str | None = getattr(request.state, "token_username", None)

    if token_group_id is None and token_username is None and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    def _extract_models(ch: Channel) -> list[dict]:
        provider = ch.provider or "unknown"
        entries: dict[str, dict] = {}
        try:
            mods: list = json.loads(ch.models or "[]")
        except Exception:
            mods = []
        for m in mods:
            mid = (m.get("id") or m.get("name")) if isinstance(m, dict) else str(m)
            if mid:
                mid = mid.removeprefix("models/")
                entries[mid] = {"id": mid, "object": "model", "created": 0, "owned_by": provider}
        try:
            mapping: dict = json.loads(ch.model_mapping or "{}")
        except Exception:
            mapping = {}
        for alias in mapping:
            if alias:
                entries[alias] = {"id": alias, "object": "model", "created": 0, "owned_by": provider}
        return list(entries.values())

    async def _channels_by_username(session, uname: str):
        from services.auth_service import get_visible_groups
        user_groups = await get_visible_groups(uname, session)
        group_ids = [g.id for g in user_groups]
        if not group_ids:
            return []
        stmt = (
            select(Channel)
            .join(GroupChannel, col(Channel.id) == col(GroupChannel.channel_id))
            .where(
                GroupChannel.group_id.in_(group_ids),
                col(Channel.enabled) == True,
            )
            .distinct()
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async with AsyncSession(engine, expire_on_commit=False) as session:
        if token_group_id:
            # 策略 1：token 绑定了特定分组，只返回该组模型
            stmt = (
                select(Channel)
                .join(GroupChannel, col(Channel.id) == col(GroupChannel.channel_id))
                .where(
                    GroupChannel.group_id == token_group_id,
                    col(Channel.enabled) == True,
                )
                .distinct()
            )
            result = await session.execute(stmt)
            channels = result.scalars().all()

        elif token_username:
            # 策略 2：token 有 username，按用户所在分组
            channels = await _channels_by_username(session, token_username)

        else:
            # 策略 3：JWT 认证
            # current_user is guaranteed non-None by the 401 guard above (if not api_key_authed and not current_user)
            username = current_user["username"]
            role = current_user["role"]
            if role in ("admin", "superadmin"):
                result = await session.execute(
                    select(Channel).where(Channel.enabled == True)
                )
                channels = result.scalars().all()
            else:
                channels = await _channels_by_username(session, username)

        model_set: dict[tuple, dict] = {}
        for ch in channels:
            for entry in _extract_models(ch):
                entry_key = (entry["id"], entry["owned_by"])
                if entry_key not in model_set:
                    model_set[entry_key] = entry

    all_models = list(model_set.values())
    logger.info(f"模型列表查询：{len(all_models)} 个模型")
    return JSONResponse(content={"object": "list", "data": all_models})


# 刷新模型配置 API
@app.post("/v1/refresh_models")
async def refresh_models(request: Request):
    """
    从后端 API 重新获取模型列表并更新配置文件

    请求体:
    {
        "group_name": "optional_group_name"  # 可选,如果提供则只刷新该分组
    }

    返回:
    {
        "status": "success",
        "message": "配置已刷新",
        "models": [...],  # 更新后的模型列表
        "total": 10       # 模型总数
    }
    """
    global config

    # 重新加载配置文件
    config = load_config()
    logger.info("配置文件已重新加载")

    # 解析请求体中的 group_name (可选)
    group_name_filter = None
    try:
        body = await request.json()
        group_name_filter = body.get("group_name")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass  # 如果没有请求体或解析失败,忽略

    if not config:
        logger.warning("配置文件为空或不存在")
        return JSONResponse(
            content={
                "status": "error",
                "message": "配置文件为空,无法刷新",
                "models": [],
                "total": 0,
            }
        )

    # 从后端重新获取模型列表
    updated_groups = []
    all_models = []
    errors = []

    for group_name, group_data in config.items():
        # 如果指定了 group_name,只处理该分组
        if group_name_filter and group_name != group_name_filter:
            continue

        base_url = group_data.get("base_url")
        api_key = group_data.get("api_key")

        if not base_url or not api_key:
            errors.append(f"分组 {group_name} 缺少 base_url 或 api_key")
            continue

        try:
            # 从后端 API 获取模型列表
            models_url = f"{base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"}

            logger.info(f"正在从 {models_url} 获取模型列表")

            async with httpx.AsyncClient(timeout=10.0, verify=not SKIP_SSL_VERIFY) as client:
                response = await client.get(models_url, headers=headers)
                response.raise_for_status()
                data = response.json()

                # 适配 OpenAI 和 Anthropic 格式
                if "data" in data:  # OpenAI 格式
                    models = data["data"]
                elif "models" in data:  # 可能的 Anthropic 格式
                    models = data["models"]
                else:
                    models = []

                # 更新配置中的模型列表
                config[group_name]["models"] = models
                updated_groups.append(group_name)

                logger.info(f"分组 {group_name} 获取到 {len(models)} 个模型")

                # 收集模型信息用于返回
                for model in models:
                    model_id = model.get("id") or model.get("name")
                    if model_id:
                        model_obj = {
                            "id": model_id,
                            "object": "model",
                            "created": model.get("created", 0),
                            "owned_by": model.get("owned_by", group_name),
                            "group": group_name,
                            "base_url": base_url,
                        }
                        all_models.append(model_obj)

        except httpx.HTTPStatusError as e:
            error_msg = f"分组 {group_name} HTTP {e.response.status_code} 错误"
            logger.error(error_msg)
            errors.append(error_msg)
        except Exception as e:
            error_msg = f"分组 {group_name} 获取模型失败: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    # 保存更新后的配置到文件
    if updated_groups:
        if save_config(config):
            logger.info(f"配置已更新并保存,刷新了 {len(updated_groups)} 个分组")
        else:
            errors.append("保存配置文件失败")

    # 构建响应消息
    if not updated_groups and errors:
        status = "error"
        message = f"刷新失败: {'; '.join(errors)}"
    elif updated_groups and errors:
        status = "partial"
        message = f"部分成功: 已刷新 {len(updated_groups)} 个分组 ({', '.join(updated_groups)}),但有错误: {'; '.join(errors)}"
    elif updated_groups:
        status = "success"
        message = f"配置已刷新,共更新 {len(all_models)} 个模型 (分组: {', '.join(updated_groups)})"
    else:
        status = "success"
        message = "没有需要刷新的分组"

    logger.info(
        f"配置刷新完成: {len(all_models)} 个模型"
        + (f" (分组: {group_name_filter})" if group_name_filter else "")
    )

    return JSONResponse(
        content={
            "status": status,
            "message": message,
            "models": all_models,
            "total": len(all_models),
            "updated_groups": updated_groups,
            "errors": errors,
        }
    )


# 健康检查端点
@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


# --------------------------------------------------------------------------- #
# Responses API 端点（对外 /v1/responses）
#
# codex 等客户端只会说 OpenAI Responses 协议。本端点把 Responses 请求转成
# Chat Completions 发给上游（上游全是 chat completions），再把上游响应转回
# Responses 格式返回。计费/限流/鉴权/日志全部复用现有链路。
#
# ⚠️ 必须注册在下方 catch-all `/v1/{path:path}` 之前，否则会被透明代理捕获。
# --------------------------------------------------------------------------- #


def _bill_and_log_response(
    request: Request,
    *,
    request_id: str,
    chat_body: dict,
    response_body: str,
    status: int,
    duration_ms: float,
    model_name: str | None,
    backend_url: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
    is_stream: bool,
) -> None:
    """非流式 Responses 请求的计费 + 日志（fire-and-forget），复用现有链路。"""
    log_task = asyncio.create_task(
        log_writer.enqueue_log({
            "timestamp": timestamp(),
            "method": request.method,
            "path": "responses",
            "request_url": backend_url,
            "request_headers": {},
            "request_body": json.dumps(chat_body, ensure_ascii=False),
            "response_status": status,
            "response_headers": {},
            "response_body": response_body,
            "duration_ms": duration_ms,
            "model_name": model_name,
            "backend_url": backend_url,
            "is_stream": is_stream,
            "token_id": getattr(request.state, "token_id", None),
            "request_id": request_id,
        })
    )
    app.state.log_tasks.add(log_task)
    log_task.add_done_callback(app.state.log_tasks.discard)

    async def _bill():
        group_id = getattr(request.state, "token_group_id", None)
        multiplier = await _get_group_multiplier(group_id)
        async with AsyncSession(engine, expire_on_commit=False) as ps:
            cost_usd = await calculate_cost(
                session=ps, group_id=group_id, model=model_name,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_creation_tokens=cache_creation_tokens, multiplier=multiplier,
            )
        await update_usage(
            token_id=getattr(request.state, "token_id", None), channel_id=None,
            model=model_name, input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=cost_usd, duration_ms=duration_ms, status=status, is_stream=False,
            username=getattr(request.state, "token_username", None),
            request_id=request_id, cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            covered_by_package=getattr(request.state, "covered_by_package", False),
        )
        if group_id:
            await _update_rate_limit_counters(
                group_id=group_id, request_id=request_id, input_tokens=input_tokens,
                output_tokens=output_tokens, cost_usd=cost_usd,
                username=getattr(request.state, "token_username", None),
            )
        await _maybe_deduct(
            covered=getattr(request.state, "covered_by_package", False),
            username=getattr(request.state, "token_username", None), cost_usd=cost_usd,
        )

    bill_task = asyncio.create_task(_bill())
    app.state.log_tasks.add(bill_task)
    bill_task.add_done_callback(app.state.log_tasks.discard)


@app.post("/v1/responses")
async def responses_endpoint(request: Request):
    """对外 Responses API 入口：转换 → 上游 chat → 转换回 Responses。"""
    # 1. 额度拦截
    quota_usd = getattr(request.state, "quota_usd", 0)
    used_usd = getattr(request.state, "used_usd", 0)
    if not check_quota(quota_usd=quota_usd, used_usd=used_usd):
        return JSONResponse(
            content={"error": {"type": "quota_exceeded", "message": "Token quota exceeded"}},
            status_code=402,
        )

    # 2. 解析 + 转换请求
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(content={"error": "invalid JSON body"}, status_code=400)

    original_model = body.get("model")
    if not original_model:
        return JSONResponse(content={"error": "No model name provided"}, status_code=400)

    chat_body = responses_to_chat_request(body)

    # 3. 路由（复用现有逻辑）
    backend_info = await find_backend_for_model(
        original_model,
        username=getattr(request.state, "token_username", None),
        group_id=getattr(request.state, "token_group_id", None),
    )
    if not backend_info:
        if not getattr(request.state, "token_username", None):
            return JSONResponse(content={"error": "anonymous token is not allowed"}, status_code=401)
        return JSONResponse(content={"error": "no available channel for this model"}, status_code=400)

    backend_url = backend_info["base_url"]
    api_key = backend_info["api_key"]
    chat_body["model"] = backend_info["model"]
    provider = backend_info.get("provider", "")
    ch_opts = {
        "proxy_url": backend_info.get("proxy_url"),
        "disable_ssl": bool(backend_info.get("disable_ssl", False)),
        "disable_compression": bool(backend_info.get("disable_compression", False)),
    }

    is_stream = bool(body.get("stream"))
    if is_stream:
        return await _forward_responses_stream(
            request, chat_body, backend_url, api_key, provider, original_model, **ch_opts)
    return await _forward_responses_nonstream(
        request, chat_body, backend_url, api_key, provider, original_model, **ch_opts)


async def _forward_responses_nonstream(
    request: Request, chat_body: dict, backend_url: str, api_key: str,
    provider: str, display_model: str | None,
    *, proxy_url: Optional[str] = None, disable_ssl: bool = False,
    disable_compression: bool = False,
) -> Response:
    """非流式：调上游 chat completions，转换响应为 Responses。"""
    start_time = time.time()
    request_id = uuid4().hex
    url = urljoin(backend_url.rstrip("/") + "/", "chat/completions")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    _apply_accept_encoding(headers, disable_compression)
    content = json.dumps(chat_body).encode("utf-8")

    async with httpx.AsyncClient(
        **_httpx_client_kwargs(TIMEOUT_BOUND, disable_ssl=disable_ssl, proxy_url=proxy_url)
    ) as client:
        resp = await client.request("POST", url, content=content, headers=headers)
        resp_bytes = resp.content

    duration_ms = (time.time() - start_time) * 1000

    if resp.status_code != 200:
        # 透传上游错误体（chat 格式）
        try:
            err_json = json.loads(resp_bytes)
        except (json.JSONDecodeError, ValueError):
            err_json = {"error": {"message": resp_bytes.decode("utf-8", errors="replace"),
                                  "code": resp.status_code}}
        return JSONResponse(content=err_json, status_code=resp.status_code)

    chat_resp = json.loads(resp_bytes)
    responses_resp = chat_resp_to_responses_resp(chat_resp)

    usage = chat_resp.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    _bill_and_log_response(
        request, request_id=request_id, chat_body=chat_body,
        response_body=resp_bytes.decode("utf-8", errors="replace"),
        status=resp.status_code, duration_ms=duration_ms, model_name=display_model,
        backend_url=backend_url,
        input_tokens=_safe_int(usage.get("prompt_tokens", 0)),
        output_tokens=_safe_int(usage.get("completion_tokens", 0)),
        cache_read_tokens=_safe_int(prompt_details.get("cached_tokens", 0)),
        cache_creation_tokens=0, is_stream=False,
    )
    return JSONResponse(content=responses_resp, status_code=200)


async def _forward_responses_stream(
    request: Request, chat_body: dict, backend_url: str, api_key: str,
    provider: str, display_model: str | None,
    *, proxy_url: Optional[str] = None, disable_ssl: bool = False,
    disable_compression: bool = False,
) -> StreamingResponse:
    """流式：上游 chat SSE → 实时转 Responses 事件。计费用原始 chat chunks。"""
    start_time = time.time()
    request_id = uuid4().hex
    url = urljoin(backend_url.rstrip("/") + "/", "chat/completions")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "Accept": "text/event-stream"}
    _apply_accept_encoding(headers, disable_compression)
    content = json.dumps(chat_body).encode("utf-8")

    raw_chunks: list[str] = []  # 原始 chat 行，给计费/日志
    response_status = 0

    async def stream_generator():
        nonlocal response_status
        state = _ResponsesStreamState(
            model=display_model,
            response_id=f"resp_{uuid4().hex}",
            msg_id=f"msg_{uuid4().hex}",
            created=int(start_time),
        )
        try:
            async with httpx.AsyncClient(
                **_httpx_client_kwargs(TIMEOUT_BOUND, disable_ssl=disable_ssl, proxy_url=proxy_url)
            ) as client:
                async with client.stream("POST", url, content=content, headers=headers) as response:
                    response_status = response.status_code
                    if response_status != 200:
                        parts = [line async for line in response.aiter_lines()]
                        body_text = "\n".join(parts)
                        raw_chunks.append(body_text)
                        try:
                            err_json = json.loads(body_text)
                        except (json.JSONDecodeError, ValueError):
                            err_json = {"error": {"message": f"上游服务异常 (HTTP {response_status})",
                                                  "code": response_status}}
                        yield f"data: {json.dumps(err_json, ensure_ascii=False)}\n\n".encode("utf-8")
                        return

                    # 前导事件
                    for et, data in state.header():
                        yield format_responses_sse(et, data).encode("utf-8")

                    async for line in response.aiter_lines():
                        raw_chunks.append(line + "\n")
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]" or not payload:
                            continue
                        try:
                            chunk = json.loads(payload)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        for et, data in state.feed(chunk):
                            yield format_responses_sse(et, data).encode("utf-8")

                    # 收尾事件
                    for et, data in state.finalize():
                        yield format_responses_sse(et, data).encode("utf-8")
        except Exception as e:
            logger.error(f"Responses 流式转发错误: {e}")
            err = {"error": {"message": str(e), "code": 0}}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
        finally:
            duration_ms = (time.time() - start_time) * 1000
            log_task = asyncio.create_task(
                log_writer.enqueue_log({
                    "timestamp": timestamp(), "method": request.method, "path": "responses",
                    "request_url": url, "request_headers": {},
                    "request_body": json.dumps(chat_body, ensure_ascii=False),
                    "response_status": response_status, "response_headers": {},
                    "response_body": "".join(raw_chunks), "duration_ms": duration_ms,
                    "model_name": display_model, "backend_url": backend_url, "is_stream": True,
                    "token_id": getattr(request.state, "token_id", None), "request_id": request_id,
                })
            )
            app.state.log_tasks.add(log_task)
            log_task.add_done_callback(app.state.log_tasks.discard)

            # 计费：用原始 chat chunks 喂现有解析（与 chat completions 渠道一致）
            finalize_task = asyncio.create_task(
                _finalize_stream_usage(
                    request=request, request_id=request_id, model_name=display_model,
                    duration_ms=duration_ms, response_status=response_status,
                    accumulated_chunks=raw_chunks, provider=provider or "openai",
                )
            )
            app.state.log_tasks.add(finalize_task)
            finalize_task.add_done_callback(app.state.log_tasks.discard)

    return StreamingResponse(
        stream_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


# 捕获所有 HTTP 方法的所有路径
@app.api_route(
    "/v1/{path:path}",
    methods=["POST"],
)
async def gateway(request: Request, path: str):
    """
    网关入口：根据模型名称动态路由到对应的后端服务
    """
    # 1. 额度检查（在转发前拦截超额请求）
    quota_usd = getattr(request.state, "quota_usd", 0)
    used_usd = getattr(request.state, "used_usd", 0)
    if not check_quota(quota_usd=quota_usd, used_usd=used_usd):
        logger.warning(
            f"Token {getattr(request.state, 'token_id', None)} 额度已超出: "
            f"used={used_usd}, quota={quota_usd}"
        )
        return JSONResponse(
            content={"error": {"type": "quota_exceeded", "message": "Token quota exceeded"}},
            status_code=402,
        )

    # 读取请求体
    body = await request.json()

    # 尝试从请求体中提取模型名称
    model_name = body.get("model")
    api_key = None
    backend_provider = ""

    if model_name:
        # 根据模型名称查找后端配置
        backend_info = await find_backend_for_model(
            model_name,
            username=getattr(request.state, "token_username", None),
            group_id=getattr(request.state, "token_group_id", None),
        )
        if backend_info:
            backend_url, api_key, model_name, backend_provider = (
                backend_info["base_url"],
                backend_info["api_key"],
                backend_info["model"],
                backend_info.get("provider", ""),
            )
            ch_proxy_url = backend_info.get("proxy_url")
            ch_disable_ssl = bool(backend_info.get("disable_ssl", False))
            ch_disable_compression = bool(backend_info.get("disable_compression", False))
            logger.info(f"Found backend for model {backend_info}")
            body["model"] = model_name
        else:
            token_username = getattr(request.state, "token_username", None)
            if not token_username:
                return JSONResponse(
                    content={"error": "anonymous token is not allowed"}, status_code=401
                )
            return JSONResponse(
                content={"error": "no available channel for this model"}, status_code=400
            )

    else:
        return JSONResponse(
            content={"error": "No model name provided"}, status_code=400
        )

    # 重新构建请求（因为已经读取了 body）
    class RequestWithBody(Request):
        async def body(self) -> bytes:
            return json.dumps(body).encode("utf-8")

    new_request = RequestWithBody(request.scope, request.receive)

    return await forward_request(
        new_request, path, backend_url, api_key, backend_provider,
        proxy_url=ch_proxy_url, disable_ssl=ch_disable_ssl,
        disable_compression=ch_disable_compression,
    )


# --------------------------------------------------------------------------- #
# React 前端静态文件服务（生产构建）
# 放在所有 API 路由之后，作为兜底处理器
# --------------------------------------------------------------------------- #
_STATIC_DIR = Path(__file__).parent.parent / "apps" / "react" / "dist"

if _STATIC_DIR.exists():
    # /assets 目录包含带 hash 的 JS/CSS 文件，可强缓存
    _assets_dir = _STATIC_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """SPA fallback：dist 根目录下存在的静态文件直接返回，否则返回 index.html 由前端路由处理"""
        file_path = _STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=GATEWAY_PORT)
