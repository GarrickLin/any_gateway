from fastapi.responses import Response, JSONResponse, StreamingResponse, FileResponse
from fastapi import FastAPI, Request, HTTPException
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
)
from loguru import logger
from urllib.parse import urljoin
from middleware.auth import AuthMiddleware
from db.database import init_db, engine
from db.models import Channel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from services.quota import check_quota, update_usage
from admin.router import token_router, channel_router, group_router, admin_router, auth_router, me_router, users_router, user_router, group_channel_router, user_group_router
import yaml
import json
import time
import asyncio
import random
import httpx
import log_writer


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
) -> Optional[Dict[str, str]]:
    """
    根据模型名称查找后端渠道。

    路由策略：
    1. 若 username 不为空，按用户所属分组的 priority 降序查找，
       在第一个支持该模型的分组内按 weight 加权随机选渠道。
    2. 若 username 为空，回退到旧逻辑：遍历所有 enabled 渠道。
    """
    from db.models import UserGroupMembership, UserGroup, GroupChannel

    def _extract_model_info(channel: Channel, req_model: str) -> Optional[Dict[str, str]]:
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
                model_ids.append(m)
            elif isinstance(m, dict):
                model_ids.append(m.get("id") or m.get("name") or "")

        all_supported = set(model_ids) | set(model_mapping.keys())
        if req_model not in all_supported:
            return None

        upstream_model = model_mapping.get(req_model, req_model)
        return {"base_url": channel.base_url, "api_key": channel.api_key, "model": upstream_model}

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

    async with AsyncSession(engine, expire_on_commit=False) as session:
        if username:
            # 1. 获取用户所属分组，按 priority 降序
            stmt = (
                select(UserGroup)
                .join(UserGroupMembership, UserGroup.id == UserGroupMembership.group_id)
                .where(UserGroupMembership.username == username)
                .order_by(UserGroup.priority.desc())
            )
            result = await session.execute(stmt)
            groups = result.scalars().all()

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

                # 3. 过滤支持该模型的渠道
                supported = [c for c in candidates if _extract_model_info(c, model_name)]
                if not supported:
                    continue

                # 4. 加权随机选一个渠道
                chosen = _weighted_choice(supported)
                return _extract_model_info(chosen, model_name)

            return None  # 所有分组均无此模型

        else:
            # 旧逻辑：遍历所有 enabled 渠道（无分组过滤，向后兼容）
            result = await session.execute(
                select(Channel).where(Channel.enabled == True)
            )
            channels = result.scalars().all()
            for channel in channels:
                info = _extract_model_info(channel, model_name)
                if info:
                    return info
            return None


async def forward_streaming_request(
    request: Request,
    path: str,
    url: str,
    headers: dict,
    body: bytes,
    backend_url: str,
    model_name: Optional[str],
    start_time: float,
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
            async with httpx.AsyncClient(timeout=TIMEOUT_BOUND) as client:
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
            # 透传错误给客户端
            error_chunk = f"data: {json.dumps({'error': error_message})}\n\n"
            accumulated_chunks.append(error_chunk)
            yield error_chunk.encode("utf-8")

        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Streaming error: {error_message}")
            error_chunk = f"data: {json.dumps({'error': error_message})}\n\n"
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
                    }
                )
            )
            app.state.log_tasks.add(task)
            task.add_done_callback(app.state.log_tasks.discard)
            logger.info(f"流式请求日志已入队, 当前task数量: {len(app.state.log_tasks)}")

            # fire-and-forget 更新用量
            # TODO: 流式响应中解析 usage 较复杂，暂时记录 0 token，后续实现
            usage_task = asyncio.create_task(
                update_usage(
                    token_id=getattr(request.state, "token_id", None),
                    channel_id=None,
                    model=model_name,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,  # TODO: 实现真实定价
                    duration_ms=duration_ms,
                    status=response_status or None,
                    is_stream=True,
                )
            )
            app.state.log_tasks.add(usage_task)
            usage_task.add_done_callback(app.state.log_tasks.discard)

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
    request: Request, path: str, backend_url: str, api_key: Optional[str] = None
) -> Response:
    """
    转发请求到后端服务并返回响应。
    如果提供了 api_key，会覆盖原请求中的 Authorization header。
    支持自动检测并转发流式响应（SSE）。
    """

    start_time = time.time()

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

    # 如果提供了 api_key，覆盖 Authorization header
    if api_key:
        headers.pop("authorization", None)
        headers.pop("Authorization", None)
        headers.pop("x-api-key", None)
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(f"Request body: {body[:200] if body else ''}")
    logger.info(f"Request headers: {headers}")
    logger.info(f"Request URL: {url}")
    logger.info(f"Forwarding {request.method} request to {url}")

    # 提取模型名称和检查是否为流式请求
    model_name = None
    is_stream_request = False
    try:
        if body:
            body_json = json.loads(body)
            model_name = body_json.get("model")
            is_stream_request = body_json.get("stream", False)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    # 如果请求要求流式，使用流式转发
    if is_stream_request:
        logger.info("检测到流式请求，使用 SSE 转发")
        return await forward_streaming_request(
            request, path, url, headers, body, backend_url, model_name, start_time
        )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_BOUND) as client:
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

            # 从响应体中提取 token 用量（支持 OpenAI 和 Anthropic 格式）
            input_tokens = 0
            output_tokens = 0
            try:
                resp_json = json.loads(response_content)
                usage = resp_json.get("usage", {})
                # OpenAI 格式: prompt_tokens / completion_tokens
                # Anthropic 格式: input_tokens / output_tokens
                input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
                output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
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
                    }
                )
            )
            app.state.log_tasks.add(task)
            task.add_done_callback(app.state.log_tasks.discard)
            logger.info(f"当前task数量: {len(app.state.log_tasks)}")

            # fire-and-forget 更新用量（不阻塞响应）
            usage_task = asyncio.create_task(
                update_usage(
                    token_id=getattr(request.state, "token_id", None),
                    channel_id=None,
                    model=model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=0.0,  # TODO: 实现真实定价
                    duration_ms=duration_ms,
                    status=response.status_code,
                    is_stream=False,
                )
            )
            request.app.state.log_tasks.add(usage_task)
            usage_task.add_done_callback(request.app.state.log_tasks.discard)

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
                }
            )
        )
        app.state.log_tasks.add(task)
        task.add_done_callback(app.state.log_tasks.discard)
        logger.info(f"当前task数量: {len(app.state.log_tasks)}")

        raise


# 模型列表 API
@app.get("/v1/models")
async def list_models():
    """
    返回所有配置的模型列表（OpenAI 格式）
    """

    if not config:
        logger.warning("配置文件为空或不存在")
        return JSONResponse(content={"object": "list", "data": []})

    # 收集所有模型
    all_models = []
    for group_name, group_data in config.items():
        models = group_data.get("models", [])
        for model in models:
            model_id = model.get("id") or model.get("name")
            if model_id:
                # 构建 OpenAI 格式的模型对象
                model_obj = {
                    "id": model_id,
                    "object": "model",
                    "created": model.get("created", 0),
                    "owned_by": model.get("owned_by", group_name),
                    "group": group_name,
                }
                all_models.append(model_obj)

    logger.info(f"返回 {len(all_models)} 个模型")

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

            async with httpx.AsyncClient(timeout=10.0) as client:
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

    if model_name:
        # 根据模型名称查找后端配置
        backend_info = await find_backend_for_model(
            model_name,
            username=getattr(request.state, "token_username", None),
        )
        if backend_info:
            backend_url, api_key, model_name = (
                backend_info["base_url"],
                backend_info["api_key"],
                backend_info["model"],
            )
            logger.info(f"Found backend for model {backend_info}")
            body["model"] = model_name
        else:
            return JSONResponse(
                content={"error": "No model name provided"}, status_code=400
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

    return await forward_request(new_request, path, backend_url, api_key)


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
        """SPA fallback：所有未匹配的 GET 请求均返回 index.html，由前端路由处理"""
        return FileResponse(_STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("__main__:app", host="0.0.0.0", port=GATEWAY_PORT)
