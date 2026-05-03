from pathlib import Path
import os

TIMEOUT_BOUND = 600
GATEWAY_PORT = 8003
FRONTEND_PORT = 8502
MAX_QUEUE_SIZE = 1000
MAX_TOKENS = 32000
NUM_LOG_CONSUMERS = int(os.getenv("NUM_LOG_CONSUMERS", 3))  # 日志消费者数量,建议 2-5
SKIP_SSL_VERIFY = os.getenv("SKIP_SSL_VERIFY", "0") == "1"  # 跳过上游 SSL 证书验证（紧急热开关，默认关闭）
LOG_BASE_DIR = Path("./data/sessions")
CONFIG_FILE = Path("./data/config.yaml")
