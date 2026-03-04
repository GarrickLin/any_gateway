#!/usr/bin/env python3
"""
Micro Gateway 统一启动脚本
同时启动网关服务和前端界面
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path
from loguru import logger
from constants import GATEWAY_PORT, FRONTEND_PORT


class ProcessManager:
    """进程管理器"""

    def __init__(self):
        self.processes = []
        self.running = True

    def start_process(self, name: str, command: list, env=None):
        """启动进程"""
        logger.info(f"启动 {name}...")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env or os.environ.copy(),
            )
            self.processes.append({"name": name, "process": process, "command": command})
            logger.success(f"✅ {name} 启动成功 (PID: {process.pid})")
            return process
        except Exception as e:
            logger.error(f"❌ {name} 启动失败: {e}")
            return None

    def check_processes(self):
        """检查进程状态"""
        for proc_info in self.processes:
            process = proc_info["process"]
            if process.poll() is not None:
                # 进程已退出
                logger.warning(f"⚠️ {proc_info['name']} 已退出 (退出码: {process.returncode})")
                return False
        return True

    def stop_all(self):
        """停止所有进程"""
        logger.info("正在停止所有服务...")
        for proc_info in self.processes:
            process = proc_info["process"]
            name = proc_info["name"]

            if process.poll() is None:  # 进程仍在运行
                logger.info(f"停止 {name} (PID: {process.pid})...")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    logger.success(f"✅ {name} 已停止")
                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ {name} 未响应，强制终止...")
                    process.kill()
                    process.wait()
                    logger.success(f"✅ {name} 已强制终止")
                except Exception as e:
                    logger.error(f"❌ 停止 {name} 时出错: {e}")


# def check_backend_available():
#     """检查后端服务是否可用"""
#     import httpx

#     try:
#         with httpx.Client(timeout=2.0) as client:
#             response = client.get(f"{BACKEND_URL}/v1/models", follow_redirects=True)
#             if response.status_code < 500:
#                 return True
#     except:
#         pass
#     return False


def main():
    """主函数"""
    logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

    # 检查依赖
    try:
        import fastapi
        import streamlit
        import httpx
        import yaml
    except ImportError as e:
        logger.error(f"❌ 缺少依赖: {e}")
        logger.info("请运行: pip install -r requirements.txt")
        sys.exit(1)

    # 检查后端是否可用
    # logger.info("检查后端服务...")
    # if not check_backend_available():
    #     logger.warning(f"⚠️ 后端服务 {BACKEND_URL} 不可用")
    #     logger.info("请确保后端服务已启动，或在启动后配置正确的后端地址")

    # 创建进程管理器
    manager = ProcessManager()

    # 注册信号处理
    def signal_handler(sig, frame):
        logger.info("\n收到中断信号，正在清理...")
        manager.running = False
        manager.stop_all()
        logger.success("✅ 所有服务已停止")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\n" + "=" * 60)
    print("🚀 Micro Gateway 启动中...")
    print("=" * 60)

    # 1. 启动网关服务
    gateway_process = manager.start_process(
        "网关服务 (Gateway)",
        [sys.executable, "-m", "uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", str(GATEWAY_PORT)],
    )

    if not gateway_process:
        logger.error("❌ 网关服务启动失败，退出")
        sys.exit(1)

    # 等待网关启动
    time.sleep(2)

    # 2. 启动前端界面
    frontend_env = os.environ.copy()
    frontend_env["STREAMLIT_SERVER_PORT"] = str(FRONTEND_PORT)
    frontend_env["STREAMLIT_SERVER_HEADLESS"] = "true"

    frontend_process = manager.start_process(
        "前端界面 (Frontend)",
        [sys.executable, "-m", "streamlit", "run", "frontend.py", "--server.port", str(FRONTEND_PORT)],
        env=frontend_env,
    )

    if not frontend_process:
        logger.error("❌ 前端界面启动失败，正在清理...")
        manager.stop_all()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ 所有服务启动成功！")
    print("=" * 60)
    print(f"\n📍 访问地址:")
    print(f"   - 前端界面: http://localhost:{FRONTEND_PORT}")
    print(f"   - 网关 API: http://localhost:{GATEWAY_PORT}")
    print(f"\n💡 提示:")
    print(f"   - 按 Ctrl+C 停止所有服务")
    print(f"   - 在前端配置页面填写网关地址: http://localhost:{GATEWAY_PORT}/v1")
    print("=" * 60 + "\n")

    # 监控进程
    try:
        while manager.running:
            if not manager.check_processes():
                logger.error("❌ 检测到服务异常退出")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()


if __name__ == "__main__":
    main()
