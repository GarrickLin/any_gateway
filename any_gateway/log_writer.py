from typing import Dict, Optional, Any
from loguru import logger
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from constants import LOG_BASE_DIR, LOG_MAX_INFLIGHT
import os
import asyncio
import json
import aiofiles
import brotli

# ==================== 核心常量 ====================
# brotli 压缩等级，4-6 为速度与压缩率平衡点；高负载时降级到 FAST 优先落盘。
COMPRESS_QUALITY = int(os.getenv("LOG_COMPRESS_QUALITY", "6"))
COMPRESS_QUALITY_FAST = int(os.getenv("LOG_COMPRESS_QUALITY_FAST", "1"))

# 在途写入并发上限，同时也是内存保护：超过即丢弃本条，避免突发流量无界堆积 OOM。
MAX_INFLIGHT = LOG_MAX_INFLIGHT
# 在途写入过半即视为高负载，压缩降级以更快落盘。
_HIGH_WATER = MAX_INFLIGHT // 2

# 专用压缩线程池：把 brotli 从默认 executor 隔离出来，
# 避免与 DB 等其它 run_in_executor 调用互相抢线程、拖慢日志落盘。
_compress_executor = ThreadPoolExecutor(
    max_workers=max(2, min(8, (os.cpu_count() or 2))),
    thread_name_prefix="log-compress",
)


# ==================== 路径与日期工具 ====================

def parse_date_str(timestamp: str) -> str:
    """
    从 ISO 8601 时间戳解析出 YYYY_MM_DD 格式的日期字符串。
    例如: 2026-03-04T08:00:00Z -> 2026_03_04
    """
    try:
        date_part = timestamp.split("T")[0]
        return date_part.replace("-", "_")
    except Exception as e:
        logger.error(f"解析时间戳日期失败: {timestamp}, 错误: {e}")
        return "unknown"


def get_request_log_path(request_id: str, date_str: str) -> Path:
    """
    返回指定请求的日志文件路径。
    路径格式：LOG_BASE_DIR / date_str / f"{request_id}.json.br"
    每个文件对应一个请求，write-once，不追加。
    """
    return LOG_BASE_DIR / date_str / f"{request_id}.json.br"


# ==================== brotli 压缩/解压工具 ====================

def _read_compressed(path: Path) -> bytes:
    """解压 brotli 文件，返回原始字节。"""
    return brotli.decompress(path.read_bytes())


def _compress(data: bytes, quality: int) -> bytes:
    """brotli 压缩字节数据。"""
    return brotli.compress(data, quality=quality)


# ==================== 核心写入逻辑 ====================

async def write_log(path: Path, log_data: dict, quality: int = COMPRESS_QUALITY):
    """
    将一条日志写入 brotli 压缩的 JSON 文件。
    Write-once：每个 request_id 对应一个文件，不追加，不加锁。
    quality: brotli 压缩等级，高负载时可传 COMPRESS_QUALITY_FAST 换取更快落盘。
    """
    loop = asyncio.get_running_loop()
    raw = json.dumps(log_data, ensure_ascii=False).encode("utf-8")
    compressed = await loop.run_in_executor(_compress_executor, _compress, raw, quality)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        await f.write(compressed)
    logger.debug(f"日志已写入: {path}")


def read_log(path: Path) -> dict:
    """
    读取并解压一个请求日志文件，返回 dict。
    同步函数，供端点通过 run_in_executor 调用。
    """
    raw = _read_compressed(path)
    return json.loads(raw)


def load_day_logs(date_dir: Path) -> list:
    """
    加载某天目录下所有 *.json.br 文件，按 timestamp 排序后返回。
    每个文件对应一个请求的完整日志。
    """
    all_logs = []
    try:
        for br_file in sorted(date_dir.glob("*.json.br")):
            try:
                log_entry = json.loads(_read_compressed(br_file))
                all_logs.append(log_entry)
            except Exception as e:
                logger.error(f"读取日志文件失败 {br_file}: {e}")
    except Exception as e:
        logger.error(f"遍历日志目录失败 {date_dir}: {e}")

    all_logs.sort(key=lambda x: x.get("timestamp", ""))
    return all_logs


# ==================== 日志写入系统（协程 + 在途限流） ====================
# 无后台队列 / worker 池：每条日志由调用方 create_task(enqueue_log(...)) 直接落盘，
# 用一个在途计数器做准入控制——达到 MAX_INFLIGHT 即丢弃本条（过载保护 + 内存有界）。
# 计数器在单线程事件循环内自增/自减，check 与 +=1 之间无 await，天然无竞态。

_inflight = 0


async def _write_one(log_data: Dict[str, Any]) -> None:
    """校验并把单条日志写盘；异常只记录、不抛出（不影响调用方）。"""
    timestamp_str = log_data.get("timestamp")
    request_id = log_data.get("request_id")

    if not timestamp_str or not request_id:
        logger.error(
            f"日志缺少 timestamp 或 request_id，丢弃: "
            f"model={log_data.get('model_name')} path={log_data.get('path')}"
        )
        return

    date_str = parse_date_str(timestamp_str)
    if date_str == "unknown":
        logger.error(
            f"时间戳无法解析，丢弃日志: request_id={request_id} timestamp={timestamp_str!r}"
        )
        return

    # 高负载时降低压缩等级，优先更快落盘
    quality = COMPRESS_QUALITY if _inflight < _HIGH_WATER else COMPRESS_QUALITY_FAST
    try:
        await write_log(get_request_log_path(request_id, date_str), log_data, quality=quality)
    except Exception as e:
        logger.error(
            f"写入日志文件失败(该条日志丢失): request_id={request_id} "
            f"model={log_data.get('model_name')} path={log_data.get('path')} 错误: {e}",
            exc_info=True,
        )


async def enqueue_log(log_data: Dict[str, Any]) -> None:
    """写入一条日志（协程直写）。达到在途上限即丢弃，避免无界堆积。

    函数名沿用 enqueue_* 以兼容既有调用方；内部已无队列。
    调用方通常以 asyncio.create_task(enqueue_log(...)) 触发，不阻塞主流程。
    """
    global _inflight
    if _inflight >= MAX_INFLIGHT:
        logger.error(
            f"在途日志写入已达上限({MAX_INFLIGHT})，丢弃日志: "
            f"request_id={log_data.get('request_id')} model={log_data.get('model_name')} "
            f"path={log_data.get('path')} status={log_data.get('response_status')}"
        )
        return

    _inflight += 1
    try:
        await _write_one(log_data)
    finally:
        _inflight -= 1


async def enqueue_rejection_log(
    request,
    *,
    status: int,
    error: str,
    model_name: Optional[str] = None,
    request_body: str = "",
    backend_url: str = "",
) -> None:
    """记录未进入转发链路即被拒绝的请求（鉴权失败 / 限流 / 额度超限 / 无可用渠道等）。

    这类请求不会到达 forward_request，若不单独补写，会话日志与后台查看器中
    将完全看不到它们。这里生成一条与转发日志同构（字段一致）的记录，
    fire-and-forget 写入，并登记到 app.state.log_tasks 以便优雅关闭时能等待其完成。
    """
    try:
        headers = dict(request.headers)
    except Exception:
        headers = {}
    headers.pop("host", None)
    headers.pop("content-length", None)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": request.method,
        "path": request.url.path,
        "request_url": str(request.url),
        "request_headers": headers,
        "request_body": request_body,
        "response_status": status,
        "response_headers": {},
        "response_body": json.dumps({"error": error}, ensure_ascii=False),
        "duration_ms": 0.0,
        "model_name": model_name,
        "backend_url": backend_url,
        "is_stream": False,
        "error": error,
        "token_id": getattr(request.state, "token_id", None),
        "request_id": uuid4().hex,
    }

    task = asyncio.create_task(enqueue_log(payload))
    try:
        log_tasks = request.app.state.log_tasks
        log_tasks.add(task)
        task.add_done_callback(log_tasks.discard)
    except AttributeError:
        # app.state.log_tasks 未初始化（如测试环境）——任务仍会独立完成
        pass
