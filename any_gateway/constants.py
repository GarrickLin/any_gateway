from pathlib import Path
import os

TIMEOUT_BOUND = 600
GATEWAY_PORT = 8003
FRONTEND_PORT = 8502
MAX_TOKENS = 32000
# 日志在途写入并发上限（同时是内存保护）：超过即丢弃本条。见 log_writer.MAX_INFLIGHT。
LOG_MAX_INFLIGHT = int(os.getenv("LOG_MAX_INFLIGHT", 512))
SKIP_SSL_VERIFY = os.getenv("SKIP_SSL_VERIFY", "0") == "1"  # 跳过上游 SSL 证书验证（紧急热开关，默认关闭）
LOG_BASE_DIR = Path("./data/sessions")
CONFIG_FILE = Path("./data/config.yaml")
