"""
log_writer 单元测试。
"""
import sys
import asyncio
import json
import brotli
from pathlib import Path
import tempfile
import pytest

_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))


def test_get_request_log_path():
    """路径格式应为 LOG_BASE_DIR/{date_str}/{request_id}.json.br"""
    from log_writer import get_request_log_path
    from constants import LOG_BASE_DIR
    path = get_request_log_path("abc123", "2026_03_07")
    assert path == LOG_BASE_DIR / "2026_03_07" / "abc123.json.br"


def test_write_log_creates_file():
    """write_log 应创建一个 brotli 压缩的 JSON 文件"""
    from log_writer import write_log
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json.br"
        data = {"request_id": "abc", "model": "gpt-4o"}
        asyncio.run(write_log(path, data))
        assert path.exists()
        raw = brotli.decompress(path.read_bytes())
        result = json.loads(raw)
        assert result == data


def test_write_log_does_not_append():
    """write_log 是 write-once，第二次调用应覆盖"""
    from log_writer import write_log
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json.br"
        asyncio.run(write_log(path, {"v": 1}))
        asyncio.run(write_log(path, {"v": 2}))
        raw = brotli.decompress(path.read_bytes())
        assert json.loads(raw) == {"v": 2}


def test_load_day_logs_reads_all_requests():
    """load_day_logs 应读取目录下所有 .json.br 文件，按 timestamp 排序返回"""
    from log_writer import write_log, load_day_logs
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir)
        asyncio.run(write_log(d / "req1.json.br", {"timestamp": "2026-03-07T01:00:00Z", "request_id": "req1"}))
        asyncio.run(write_log(d / "req2.json.br", {"timestamp": "2026-03-07T02:00:00Z", "request_id": "req2"}))
        logs = load_day_logs(d)
        assert len(logs) == 2
        assert logs[0]["request_id"] == "req1"
        assert logs[1]["request_id"] == "req2"


def test_log_consumer_skips_missing_fields():
    """log_consumer 遇到缺少 request_id 或 timestamp 的日志应跳过，不写文件"""
    import tempfile
    from unittest.mock import patch

    async def _run():
        import log_writer
        log_writer.log_queue = asyncio.Queue()

        # 入队一条缺少 request_id 的日志
        await log_writer.log_queue.put({"timestamp": "2026-03-07T10:00:00Z"})
        # 入队关闭信号
        await log_writer.log_queue.put(None)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_writer.LOG_BASE_DIR", Path(tmpdir)):
                await log_writer.log_consumer()
            # 不应有文件被写入
            assert list(Path(tmpdir).rglob("*.json.br")) == []

    asyncio.run(_run())
