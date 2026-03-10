from pathlib import Path
import os

TIMEOUT_BOUND = 600
GATEWAY_PORT = 8003
FRONTEND_PORT = 8502
MAX_QUEUE_SIZE = 1000
MAX_TOKENS = 32000
NUM_LOG_CONSUMERS = int(os.getenv("NUM_LOG_CONSUMERS", 3))  # 日志消费者数量,建议 2-5
LOG_BASE_DIR = Path("./data/sessions")
CONFIG_FILE = Path("./data/config.yaml")
