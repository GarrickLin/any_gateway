from typing import Dict, Optional, Any
from loguru import logger
from pathlib import Path
from constants import LOG_BASE_DIR
import asyncio
import json
import aiofiles
import brotli

# ==================== 核心常量 ====================
COMPRESS_QUALITY = 6   # brotli 压缩等级，4-6 为速度与压缩率平衡点


# ==================== 路径与日期工具 ====================

def _parse_date_str(timestamp: str) -> str:
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


def _compress(data: bytes) -> bytes:
    """brotli 压缩字节数据。"""
    return brotli.compress(data, quality=COMPRESS_QUALITY)


# ==================== 核心写入逻辑 ====================

async def write_log(path: Path, log_data: dict):
    """
    将一条日志写入 brotli 压缩的 JSON 文件。
    Write-once：每个 request_id 对应一个文件，不追加，不加锁。
    """
    loop = asyncio.get_running_loop()
    raw = json.dumps(log_data, ensure_ascii=False).encode("utf-8")
    compressed = await loop.run_in_executor(None, _compress, raw)
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


# ==================== 日志队列系统 ====================

log_queue: Optional[asyncio.Queue] = None


async def log_consumer():
    """后台日志消费者任务 - 从队列中取出日志并写入文件"""
    global log_queue

    if log_queue is None:
        logger.error("日志队列未初始化")
        return

    logger.info("日志消费者任务已启动")
    LOG_BASE_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            log_data = await log_queue.get()

            if log_data is None:
                logger.info("日志消费者收到关闭信号")
                break

            try:
                timestamp_str = log_data.get("timestamp")
                request_id = log_data.get("request_id")

                if not timestamp_str or not request_id:
                    logger.warning("日志数据缺少 timestamp 或 request_id 字段，跳过")
                else:
                    date_str = _parse_date_str(timestamp_str)
                    if date_str == "unknown":
                        logger.error(f"无法解析时间戳，跳过日志记录: {timestamp_str}")
                        log_queue.task_done()
                        continue
                    log_file_path = get_request_log_path(request_id, date_str)
                    await write_log(log_file_path, log_data)

            except Exception as e:
                logger.error(f"写入日志文件失败: {e}", exc_info=True)
            finally:
                log_queue.task_done()

        except Exception as e:
            logger.error(f"日志消费者处理错误: {e}", exc_info=True)
            await asyncio.sleep(0.1)


async def enqueue_log(log_data: Dict[str, Any]):
    """将日志数据加入队列 - 非阻塞异步操作"""
    global log_queue

    if log_queue is None:
        logger.warning("日志队列未初始化，跳过日志记录")
        return

    try:
        await asyncio.wait_for(log_queue.put(log_data), timeout=60.0)
    except asyncio.TimeoutError:
        logger.warning("日志队列已满，丢弃本次日志")
    except Exception as e:
        logger.error(f"加入日志队列失败: {e}")
