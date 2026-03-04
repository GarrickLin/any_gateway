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
CHUNK_SIZE = 65536     # 64KB，分块读取

# per-file 异步锁注册表。随用户数增加而增长，进程重启前不会清理。
# 当前为团队内部工具，用户数有限，YAGNI。
# 若未来用户规模扩大，可改用 LRU 缓存替代。
_file_locks: Dict[Path, asyncio.Lock] = {}


# ==================== 路径与日期工具 ====================

def _parse_date_str(timestamp: str) -> str:
    """
    从 ISO 8601 时间戳解析出 YYYY_MM_DD 格式的日期字符串。
    例如: 2026-03-04T08:00:00Z -> 2026_03_04
    """
    try:
        date_part = timestamp.split("T")[0]   # "2026-03-04"
        return date_part.replace("-", "_")     # "2026_03_04"
    except Exception as e:
        logger.error(f"解析时间戳日期失败: {timestamp}, 错误: {e}")
        return "unknown"


def get_user_day_log_path(token_id: str, date_str: str) -> Path:
    """
    返回指定用户在指定日期的日志文件路径。

    参数：
      token_id: Token ID 字符串，来自 log_data["token_id"]，不存在时用 "anonymous"
      date_str: 日期字符串，格式 YYYY_MM_DD（从 timestamp 中解析）
    返回：LOG_BASE_DIR / date_str / f"{token_id}.jsonl.br"
    """
    return LOG_BASE_DIR / date_str / f"{token_id}.jsonl.br"


# ==================== brotli 压缩/解压工具 ====================

def _read_all_bytes(path: Path) -> bytes:
    """
    用 brotli.Decompressor() 流式解压文件，返回原始 JSONL 字节。
    """
    decompressor = brotli.Decompressor()
    result = bytearray()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            uncompressed = decompressor.process(chunk)
            result.extend(uncompressed)

    return bytes(result)


def _compress_bytes(data: bytes) -> bytes:
    """
    用 brotli.Compressor(quality=COMPRESS_QUALITY) 流式压缩，返回压缩字节。
    """
    compressor = brotli.Compressor(quality=COMPRESS_QUALITY)
    result = bytearray()

    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i:i + CHUNK_SIZE]
        compressed = compressor.process(chunk)
        if compressed:
            result.extend(compressed)

    remainder = compressor.finish()
    if remainder:
        result.extend(remainder)

    return bytes(result)


# ==================== 核心写入逻辑 ====================

async def append_log(path: Path, log_data: dict):
    """
    线程安全地追加一条日志到 brotli 压缩的 JSONL 文件。
    流程：获取锁 -> 读-解压-追加-重压-写回
    """
    lock = _file_locks.setdefault(path, asyncio.Lock())
    async with lock:
        loop = asyncio.get_event_loop()

        # 1. 异步读取解压（原同步调用改为 executor）
        existing_bytes = b""
        if path.exists():
            try:
                existing_bytes = await loop.run_in_executor(None, _read_all_bytes, path)
            except brotli.error as e:
                logger.warning(f"brotli 解压失败，文件可能损坏，将覆盖: {path}, 错误: {e}")
                existing_bytes = b""  # 降级处理（Fix 3 合并进来）

        # 2. 拼接新行
        new_line = (json.dumps(log_data, ensure_ascii=False) + "\n").encode("utf-8")
        updated = existing_bytes + new_line

        # 3. 异步压缩（原同步调用改为 executor）
        compressed = await loop.run_in_executor(None, _compress_bytes, updated)

        # 4. 异步写回
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(compressed)

        logger.debug(f"日志已追加: {path}")


def load_day_logs(date_dir: Path) -> list:
    """
    加载某天目录下所有 *.jsonl.br 文件，合并解压，按 timestamp 排序后返回。
    """
    all_logs = []

    try:
        for br_file in sorted(date_dir.glob("*.jsonl.br")):
            try:
                raw_bytes = _read_all_bytes(br_file)
                text = raw_bytes.decode("utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            log_entry = json.loads(line)
                            all_logs.append(log_entry)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析日志行失败 {br_file}: {e}")
            except Exception as e:
                logger.error(f"读取日志文件失败 {br_file}: {e}")
    except Exception as e:
        logger.error(f"遍历日志目录失败 {date_dir}: {e}")

    # 按 timestamp 排序
    all_logs.sort(key=lambda x: x.get("timestamp", ""))

    return all_logs


# ==================== 日志队列系统 ====================

# 全局日志队列
log_queue: Optional[asyncio.Queue] = None


async def log_consumer():
    """后台日志消费者任务 - 从队列中取出日志并写入文件"""
    global log_queue

    if log_queue is None:
        logger.error("日志队列未初始化")
        return

    logger.info("日志消费者任务已启动")

    # 确保日志基础目录存在
    LOG_BASE_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            # 等待日志数据
            log_data = await log_queue.get()

            # 特殊标记用于关闭消费者
            if log_data is None:
                logger.info("日志消费者收到关闭信号")
                break

            # 处理日志写入
            try:
                timestamp_str = log_data.get("timestamp")
                if not timestamp_str:
                    logger.warning("日志数据缺少 timestamp 字段,跳过")
                else:
                    # 解析 token_id（不存在时降级为 "anonymous"）
                    token_id = log_data.get("token_id", "anonymous")
                    date_str = _parse_date_str(timestamp_str)
                    if date_str == "unknown":
                        logger.error(f"无法解析时间戳，跳过日志记录: {timestamp_str}")
                        log_queue.task_done()
                        continue
                    log_file_path = get_user_day_log_path(token_id, date_str)

                    # 追加写入日志
                    await append_log(log_file_path, log_data)

                    logger.debug(f"日志已写入: {log_file_path}")

            except Exception as e:
                logger.error(f"写入日志文件失败: {e}", exc_info=True)
            finally:
                # 无论成功、失败、还是数据无效,都必须调用 task_done
                log_queue.task_done()

        except Exception as e:
            logger.error(f"日志消费者处理错误: {e}", exc_info=True)
            await asyncio.sleep(0.1)  # 避免错误循环过快


async def enqueue_log(log_data: Dict[str, Any]):
    """将日志数据加入队列 - 非阻塞异步操作"""
    global log_queue

    if log_queue is None:
        logger.warning("日志队列未初始化,跳过日志记录")
        return

    try:
        # 使用超时避免永久阻塞,如果队列满了就丢弃日志
        await asyncio.wait_for(log_queue.put(log_data), timeout=60.0)
    except asyncio.TimeoutError:
        logger.warning("日志队列已满,丢弃本次日志")
    except Exception as e:
        logger.error(f"加入日志队列失败: {e}")
