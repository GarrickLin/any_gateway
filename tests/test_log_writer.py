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


def test_enqueue_log_skips_missing_fields():
    """enqueue_log 遇到缺少 request_id 或 timestamp 的日志应跳过，不写文件"""
    from unittest.mock import patch

    async def _run():
        import log_writer
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_writer.LOG_BASE_DIR", Path(tmpdir)):
                # 缺 request_id
                await log_writer.enqueue_log({"timestamp": "2026-03-07T10:00:00Z"})
                assert list(Path(tmpdir).rglob("*.json.br")) == []

    asyncio.run(_run())


def test_enqueue_log_writes_file_directly():
    """enqueue_log 是协程直写：无需队列/consumer，调用即落盘。"""
    from unittest.mock import patch

    async def _run():
        import log_writer
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_writer.LOG_BASE_DIR", Path(tmpdir)):
                await log_writer.enqueue_log(
                    {"timestamp": "2026-03-07T10:00:00Z", "request_id": "rX", "model_name": "m"}
                )
                files = list(Path(tmpdir).rglob("*.json.br"))
                assert [p.name for p in files] == ["rX.json.br"]

    asyncio.run(_run())


def test_enqueue_log_drops_when_inflight_at_cap():
    """在途写入达到 MAX_INFLIGHT 时应丢弃本条（过载保护），不写文件。"""
    from unittest.mock import patch

    async def _run():
        import log_writer
        orig = log_writer._inflight
        log_writer._inflight = log_writer.MAX_INFLIGHT  # 模拟已达上限
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch("log_writer.LOG_BASE_DIR", Path(tmpdir)):
                    await log_writer.enqueue_log(
                        {"timestamp": "2026-03-07T10:00:00Z", "request_id": "r1"}
                    )
                    assert list(Path(tmpdir).rglob("*.json.br")) == []
        finally:
            log_writer._inflight = orig

    asyncio.run(_run())


class _FakeState:
    token_id = 7


class _FakeApp:
    class state:
        log_tasks = set()


class _FakeURL:
    path = "/v1/chat/completions"

    def __str__(self):
        return "http://gw/v1/chat/completions?beta=true"


class _FakeRequest:
    """最小化的 Request 替身，仅提供 enqueue_rejection_log 用到的属性。"""
    method = "POST"
    url = _FakeURL()
    headers = {"authorization": "Bearer sk-x", "host": "gw", "content-length": "3"}
    state = _FakeState()
    app = _FakeApp()


def test_enqueue_rejection_log_writes_wellformed_entry():
    """被拒绝的请求应落盘一条与转发日志同构的记录。"""
    from unittest.mock import patch

    async def _run():
        import log_writer
        req = _FakeRequest()
        tasks = req.app.state.log_tasks
        tasks.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("log_writer.LOG_BASE_DIR", Path(tmpdir)):
                await log_writer.enqueue_rejection_log(
                    req, status=402, error="Token quota exceeded",
                    model_name="gpt-4o", request_body='{"model":"gpt-4o"}',
                )
                # helper 是 fire-and-forget（内部 create_task），等待写入任务完成
                await asyncio.gather(*list(tasks))
                files = list(Path(tmpdir).rglob("*.json.br"))
                assert len(files) == 1
                entry = json.loads(brotli.decompress(files[0].read_bytes()))

        assert entry["request_id"]
        assert entry["timestamp"].endswith("Z")
        assert entry["response_status"] == 402
        assert entry["model_name"] == "gpt-4o"
        assert entry["token_id"] == 7
        assert entry["error"] == "Token quota exceeded"
        assert json.loads(entry["response_body"]) == {"error": "Token quota exceeded"}
        # 代理相关头应被剔除
        assert "host" not in entry["request_headers"]
        assert "content-length" not in entry["request_headers"]

    asyncio.run(_run())
