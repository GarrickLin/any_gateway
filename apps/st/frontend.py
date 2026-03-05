import streamlit as st
import httpx
from datetime import datetime, date, timezone
import json
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger
import traceback
import sys
from any_gateway.constants import GATEWAY_PORT, LOG_BASE_DIR, MAX_TOKENS
from log_visualizer import vis_request, vis_response

# any_gateway 未安装为包，通过 sys.path 导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "any_gateway"))
from any_gateway.log_writer import load_day_logs

# 配置
GATEWAY_BASE_URL = f"http://localhost:{GATEWAY_PORT}/v1"  # 网关地址
DATA_DIR = Path("./data")
CONFIG_FILE = DATA_DIR / "config.yaml"
# CHAT_HISTORY_FILE = DATA_DIR / "chat_history.json"

st.set_page_config(page_title="Micro Gateway 管理平台", page_icon="🚀", layout="wide")


# ==================== 数据持久化工具 ====================
def ensure_data_dir():
    """确保数据目录存在"""
    DATA_DIR.mkdir(exist_ok=True)


def load_config() -> Dict[str, Any]:
    """从 YAML 文件加载配置"""
    ensure_data_dir()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            st.error(f"加载配置文件失败: {str(e)}")
            return {}
    return {}


def save_config(config: Dict[str, Any]):
    """保存配置到 YAML 文件"""
    ensure_data_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        st.error(f"保存配置文件失败: {str(e)}")


# def save_chat_history(history: List[Dict[str, Any]]):
#     """保存聊天历史到 JSON 文件"""
#     ensure_data_dir()
#     try:
#         with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
#             json.dump(history, f, ensure_ascii=False, indent=2)
#     except Exception as e:
#         logger.error(f"保存聊天历史失败: {e}")


def load_gateway_logs(selected_date: date) -> List[Dict[str, Any]]:
    """从网关日志目录加载指定日期的所有日志（brotli 压缩 JSONL 格式）"""
    date_str = selected_date.strftime("%Y_%m_%d")
    date_dir = LOG_BASE_DIR / date_str

    if not date_dir.exists():
        logger.info(f"日志目录不存在: {date_dir}")
        return []

    return load_day_logs(date_dir)


# ==================== 数据存储 ====================
# 初始化 session_state 并从文件加载数据
if "groups" not in st.session_state:
    st.session_state.groups = load_config()

# 当前会话的消息历史（仅用于 API 上下文）
if "current_session_messages" not in st.session_state:
    st.session_state.current_session_messages = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ==================== 工具函数 ====================
def fetch_models(base_url: str, api_key: str) -> Optional[List[Dict[str, Any]]]:
    """从指定的 API 地址获取模型列表"""
    try:
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        logger.info(f"正在请求模型列表: {url}")
        logger.info(f"请求头: {headers}")

        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)

            # 记录响应状态
            logger.info(f"响应状态码: {response.status_code}")

            # 如果失败，记录响应内容
            if response.status_code >= 400:
                logger.error(f"响应内容: {response.text}")

            response.raise_for_status()
            data = response.json()

            # 适配 OpenAI 和 Anthropic 格式
            if "data" in data:  # OpenAI 格式
                return data["data"]
            elif "models" in data:  # 可能的 Anthropic 格式
                return data["models"]
            else:
                return []
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code} 错误"
        error_detail = ""
        try:
            error_detail = f"\n\n错误详情: {e.response.text}"
        except:
            pass

        logger.error(f"获取模型列表失败: {error_msg} - URL: {url}{error_detail}")
        st.error(
            f"❌ 获取模型列表失败: {error_msg}\n\n"
            f"请求 URL: `{url}`{error_detail}\n\n"
            f"💡 提示:\n"
            f"- 如果通过网关访问，填写: `http://localhost:{GATEWAY_PORT}/v1`\n"
            f"- 如果直接访问后端，填写: `http://localhost:4000/v1`"
        )
        return None
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        st.error(f"❌ 获取模型列表失败: {str(e)}\n\n请求 URL: `{url}`")
        return None


def call_chat_api(
    base_url: str,
    api_key: str,
    model: str,
    provider: str,
    messages: List[Dict[str, str]],
) -> Optional[str]:
    """调用聊天 API"""
    try:
        if provider == "OpenAI":
            url = f"{base_url.rstrip('/')}/chat/completions"
        elif provider == "Anthropic":
            url = f"{base_url.rstrip('/')}/messages"
        else:
            st.error(f"不支持的 API 提供商 {provider}")
            return None
        headers = {
            "Authorization": f"Bearer {api_key}",
            # "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages}

        if provider == "Anthropic":
            payload["max_tokens"] = MAX_TOKENS

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # 提取回复内容
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            elif "content" in data:
                return data["content"][0]["text"]
            else:
                return None
    except Exception as e:
        logger.error(f"调用聊天 API 失败: {e}")
        st.error(traceback.format_exc())
        st.error(f"调用聊天 API 失败: {str(e)}")
        return None


# ==================== 页面1: 对话页面 ====================
def chat_page():
    st.title("💬 对话")

    # 检查是否有配置的 group
    if not st.session_state.groups:
        st.warning("⚠️ 请先在「配置管理」页面创建模型分组")
        return

    # 选择 Group 和模型
    col1, col2 = st.columns(2)

    with col1:
        selected_group = st.selectbox(
            "选择模型分组", options=list(st.session_state.groups.keys())
        )

    with col2:
        if selected_group:
            group_data = st.session_state.groups[selected_group]
            models = group_data.get("models", [])

            if not models:
                st.warning("该分组下没有可用模型")
                return

            # 提取模型 ID
            model_ids = [m.get("id") or m.get("name") for m in models]
            selected_model = st.selectbox("选择模型", options=model_ids)
        else:
            selected_model = None

    st.divider()

    # 会话信息
    col_info1, col_info2 = st.columns([6, 1])
    with col_info1:
        if st.session_state.current_session_messages:
            st.caption(
                f"💬 当前会话包含 {len(st.session_state.current_session_messages)} 条消息"
            )
        else:
            st.caption("💬 开始新的对话")
    with col_info2:
        if st.button("🗑️ 清空会话"):
            st.session_state.current_session_messages = []
            st.rerun()

    # 显示当前会话的对话历史
    for msg in st.session_state.current_session_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # 输入框
    if prompt := st.chat_input("输入消息..."):
        if not selected_model:
            st.error("请选择模型")
            return

        # 显示用户消息
        with st.chat_message("user"):
            st.write(prompt)

        # 将用户消息添加到当前会话
        st.session_state.current_session_messages.append(
            {"role": "user", "content": prompt}
        )

        # 调用 API（发送完整的会话历史）
        group_data = st.session_state.groups[selected_group]

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response = call_chat_api(
                    base_url=GATEWAY_BASE_URL,  # 统一通过网关访问
                    api_key=group_data["api_key"],
                    model=f"{selected_group}/{selected_model}",
                    provider=group_data["provider"],
                    messages=st.session_state.current_session_messages,
                )

            if response:
                st.write(response)

                # 将助手回复添加到当前会话
                st.session_state.current_session_messages.append(
                    {"role": "assistant", "content": response}
                )

                # 保存到全局历史（用于日志查看）
                st.session_state.chat_history.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "group": selected_group,
                        "model": selected_model,
                        "user_msg": prompt,
                        "assistant_msg": response,
                    }
                )
                # 持久化到文件
                # save_chat_history(st.session_state.chat_history)
            else:
                st.error(traceback.format_exc())
                st.error("获取响应失败")


# ==================== 页面2: 配置管理 ====================
def config_page():
    st.title("⚙️ 配置管理")

    # 添加说明
    st.info(
        "💡 **配置提示**\n\n"
        "使用 `python main.py` 启动服务后，请在此配置模型分组：\n"
        f"- API 地址填写网关地址: `http://localhost:{GATEWAY_PORT}/v1`\n"
        "- 填写后端 API 密钥并保存，系统会自动获取可用模型列表"
    )

    tab1, tab2 = st.tabs(["创建/编辑分组", "查看/删除分组"])

    # Tab 1: 创建/编辑分组
    with tab1:
        st.subheader("创建或编辑模型分组")

        # 选择是创建新分组还是编辑现有分组
        operation = st.radio(
            "操作类型", ["创建新分组", "编辑现有分组"], horizontal=True
        )

        if operation == "编辑现有分组":
            if not st.session_state.groups:
                st.info("暂无分组可编辑")
                return

            edit_group = st.selectbox(
                "选择要编辑的分组", list(st.session_state.groups.keys())
            )
            existing_data = st.session_state.groups[edit_group]

            group_name = edit_group
            default_provider = existing_data["provider"]
            default_api_key = existing_data["api_key"]
            default_base_url = existing_data["base_url"]
        else:
            group_name = ""
            default_provider = "OpenAI"
            default_api_key = ""
            default_base_url = f"http://localhost:{GATEWAY_PORT}/v1"  # 默认使用网关地址

        with st.form("group_form"):
            if operation == "创建新分组":
                group_name_input = st.text_input(
                    "分组名称", value=group_name, placeholder="例如: openai-prod"
                )
            else:
                group_name_input = group_name
                st.info(f"正在编辑分组: **{group_name}**")

            options = ["OpenAI", "Anthropic"]
            provider = st.selectbox(
                "协议提供商",
                options=options,
                index=(
                    options.index(default_provider)
                    if default_provider in options
                    else 0
                ),
            )

            api_key = st.text_input("API 密钥", value=default_api_key, type="password")
            base_url = st.text_input(
                "API 地址",
                value=default_base_url,
                placeholder=f"推荐: http://localhost:{GATEWAY_PORT}/v1 (网关地址)",
                help="⚠️ 配置说明：\n"
                f"• 推荐使用网关地址: http://localhost:{GATEWAY_PORT}/v1\n"
                "• 直接访问后端: http://localhost:4000/v1\n"
                "• 必须包含完整路径（如 /v1）\n"
                "• 程序会自动拼接 /models 和 /chat/completions",
            )

            submitted = st.form_submit_button("💾 保存并获取模型")

            if submitted:
                if not group_name_input or not api_key or not base_url:
                    st.error("❌ 所有字段都必须填写")
                else:
                    # 验证并获取模型列表
                    with st.spinner("正在获取模型列表..."):
                        models = fetch_models(base_url, api_key)

                    if models is not None:
                        st.session_state.groups[group_name_input] = {
                            "provider": provider,
                            "api_key": api_key,
                            "base_url": base_url,
                            "models": models,
                        }
                        # 持久化到文件
                        save_config(st.session_state.groups)
                        st.success(
                            f"✅ 分组 '{group_name_input}' 保存成功,获取到 {len(models)} 个模型"
                        )
                        # st.rerun()

    # Tab 2: 查看/删除分组
    with tab2:
        st.subheader("已配置的分组")

        if not st.session_state.groups:
            st.info("暂无配置的分组")
            return

        for group_name, group_data in st.session_state.groups.items():
            with st.expander(f"📦 {group_name} ({group_data['provider']})"):
                st.write(f"**API 地址:** {group_data['base_url']}")
                st.write(f"**API 密钥:** {'*' * 20}")
                st.write(f"**模型数量:** {len(group_data.get('models', []))}")

                if group_data.get("models"):
                    st.write("**可用模型:**")
                    for model in group_data["models"]:
                        model_id = model.get("id") or model.get("name", "Unknown")
                        st.write(f"- {model_id}")

                # 按钮布局：刷新和删除并排
                col_btn1, col_btn2 = st.columns(2)

                with col_btn1:
                    if st.button(f"🔄 刷新模型", key=f"refresh_{group_name}"):
                        with st.spinner("正在刷新模型列表..."):
                            try:
                                # 调用网关的 refresh_models API
                                url = f"{GATEWAY_BASE_URL}/refresh_models"
                                headers = {"Content-Type": "application/json"}
                                payload = {"group_name": group_name}

                                with httpx.Client(timeout=10.0) as client:
                                    response = client.post(
                                        url, headers=headers, json=payload
                                    )
                                    response.raise_for_status()
                                    data = response.json()

                                    # 更新本地配置
                                    if data.get("status") == "success":
                                        models = data.get("models", [])
                                        st.session_state.groups[group_name][
                                            "models"
                                        ] = models
                                        save_config(st.session_state.groups)
                                        st.success(
                                            f"✅ {data.get('message', '刷新成功')}"
                                        )
                                        st.rerun()
                                    else:
                                        st.error(
                                            f"❌ 刷新失败: {data.get('message', '未知错误')}"
                                        )
                            except httpx.HTTPStatusError as e:
                                st.error(
                                    f"❌ HTTP {e.response.status_code} 错误: {e.response.text}"
                                )
                            except Exception as e:
                                logger.error(f"刷新模型列表失败: {e}")
                                st.error(f"❌ 刷新失败: {str(e)}")

                with col_btn2:
                    if st.button(f"🗑️ 删除分组", key=f"delete_{group_name}"):
                        del st.session_state.groups[group_name]
                        # 持久化到文件
                        save_config(st.session_state.groups)
                        st.success(f"已删除分组: {group_name}")
                        st.rerun()


# ==================== 页面3: 日志查看 ====================
def logs_page():
    st.title("📊 网关日志查看")

    st.info(
        "💡 **日志说明**\n\n"
        "此页面显示网关转发的所有 HTTP 请求/响应日志,包括:\n"
        "- 请求详情 (URL, 方法, 请求头, 请求体)\n"
        "- 响应详情 (状态码, 响应头, 响应体)\n"
        "- 性能指标 (耗时)\n"
        "- 模型信息 (模型名称, 后端 URL)"
    )

    # 日期选择和过滤
    col1, col2, col3 = st.columns([6, 1, 1])

    with col1:
        selected_date = st.date_input("选择日期", value=date.today())

    with col2:
        if st.button("🔄 刷新"):
            st.rerun()

    with col3:
        show_errors_only = st.checkbox("仅错误", value=False)

    st.divider()

    # 加载网关日志
    with st.spinner("正在加载日志..."):
        gateway_logs = load_gateway_logs(selected_date)

    if not gateway_logs:
        st.warning(f"📭 在 {selected_date} 没有找到网关日志")
        st.caption(
            f"日志存储路径: `{LOG_BASE_DIR / selected_date.strftime('%Y_%m_%d')}`"
        )
        return

    # 过滤错误日志
    if show_errors_only:
        filtered_logs = [
            log
            for log in gateway_logs
            if log.get("response_status", 200) >= 400
            or log.get("response_status", 0) <= 0
        ]
    else:
        filtered_logs = gateway_logs

    # 统计信息
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)

    with col_stat1:
        st.metric("总请求数", len(gateway_logs))
    with col_stat2:
        success_count = len(
            [log for log in gateway_logs if log.get("response_status", 0) < 400]
        )
        st.metric("成功请求", success_count)
    with col_stat3:
        error_count = len(
            [log for log in gateway_logs if log.get("response_status", 0) >= 400]
        )
        st.metric("失败请求", error_count, delta_color="inverse")
    with col_stat4:
        avg_duration = (
            sum(log.get("duration_ms", 0) for log in gateway_logs) / len(gateway_logs)
            if gateway_logs
            else 0
        )
        st.metric("平均耗时", f"{avg_duration:.0f} ms")

    st.divider()

    if not filtered_logs:
        st.warning(f"📭 没有找到符合条件的日志")
        return

    # 分页控制
    col_page0, col_page1, col_page2, col_page3, col_page4, col_page5 = st.columns(
        [1, 1, 1, 2, 1, 1]
    )

    with col_page0:
        page_size = st.selectbox("每页", [10, 20, 50, 100], index=1)

    # 分页计算
    total_logs = len(filtered_logs)
    total_pages = (total_logs + page_size - 1) // page_size  # 向上取整

    # 初始化当前页码
    if "current_page" not in st.session_state:
        st.session_state.current_page = 1

    # 重置页码为1的情况
    if st.session_state.current_page > total_pages:
        st.session_state.current_page = 1

    with col_page1:
        if st.button("⏮️ 首页", disabled=st.session_state.current_page == 1):
            st.session_state.current_page = 1
            st.rerun()

    with col_page2:
        if st.button("◀️ 上页", disabled=st.session_state.current_page == 1):
            st.session_state.current_page -= 1
            st.rerun()

    with col_page3:
        st.markdown(
            f"第 **{st.session_state.current_page}** / **{total_pages}** 页 (共 **{total_logs}** 条)"
        )

    with col_page4:
        if st.button("下页 ▶️", disabled=st.session_state.current_page == total_pages):
            st.session_state.current_page += 1
            st.rerun()

    with col_page5:
        if st.button("末页 ⏭️", disabled=st.session_state.current_page == total_pages):
            st.session_state.current_page = total_pages
            st.rerun()

    st.divider()

    # 计算当前页的日志范围
    start_idx = (st.session_state.current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_logs)

    # 反转列表以最新的在前,然后切片
    reversed_logs = list(reversed(filtered_logs))
    current_page_logs = reversed_logs[start_idx:end_idx]

    # 显示日志
    for idx, log in enumerate(current_page_logs):
        # 计算全局索引
        global_idx = total_logs - start_idx - idx

        timestamp_str = log.get("timestamp")
        if timestamp_str:
            try:
                utc_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                timestamp_display = utc_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except:
                timestamp_display = timestamp_str

        method = log.get("method", "?")
        path = log.get("path", "?")
        status = log.get("response_status", 0)
        duration = log.get("duration_ms", 0)
        model_name = log.get("model_name", "N/A")

        # 状态码颜色
        if status == 0:
            status_emoji = "❌"
            status_color = "red"
        elif status < 400:
            status_emoji = "✅"
            status_color = "green"
        else:
            status_emoji = "⚠️"
            status_color = "orange"

        with st.expander(
            f"{status_emoji} {timestamp_display} | {method} /{path} | {duration:.0f}ms | {model_name}"
        ):
            # 基本信息
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.write(f"**时间戳:** {timestamp_str}")
                st.write(f"**请求方法:** {method}")
                st.write(f"**请求路径:** {path}")
                st.write(f"**完整 URL:** {log.get('request_url', 'N/A')}")
            with col_info2:
                st.write(f"**响应状态:** :{status_color}[{status}]")
                st.write(f"**耗时:** {duration:.2f} ms")
                st.write(f"**模型名称:** {model_name}")
                st.write(f"**后端 URL:** {log.get('backend_url', 'N/A')}")

            # 请求详情
            with st.container():
                st.markdown("### 📤 请求详情")

                with st.expander("请求头", expanded=False):
                    st.json(log.get("request_headers", {}))

                with st.expander("请求体", expanded=False):
                    request_body = log.get("request_body", "")
                    if request_body:
                        try:
                            # 尝试格式化 JSON
                            body_json = json.loads(request_body)
                            st.json(body_json)
                        except:
                            st.code(request_body, language="text")
                    else:
                        st.caption("(空)")

                with st.expander("请求内容", expanded=True):
                    vis_request(log.get("request_body"))

            # 响应详情
            with st.container():
                st.markdown("### 📥 响应详情")

                with st.expander("响应头", expanded=False):
                    st.json(log.get("response_headers", {}))

                with st.expander("响应体", expanded=False):
                    response_body = log.get("response_body", "")
                    if response_body:
                        # 检查是否是错误信息
                        if response_body.startswith("Error:"):
                            st.error(response_body)
                        else:
                            try:
                                # 尝试格式化 JSON
                                body_json = json.loads(response_body)
                                st.json(body_json)
                            except:
                                st.code(response_body, language="text")
                    else:
                        st.caption("(空)")

                with st.expander("响应内容", expanded=True):
                    vis_response(log.get("response_body"))

    # 底部分页控制
    st.divider()
    col_page_bottom1, col_page_bottom2, col_page_bottom3 = st.columns([1, 2, 1])

    with col_page_bottom1:
        if st.button("⬆️ 返回顶部"):
            st.rerun()

    with col_page_bottom2:
        st.markdown(f"第 **{st.session_state.current_page}** / **{total_pages}** 页")

    with col_page_bottom3:
        pass  # 占位

    # 导出功能
    st.divider()
    col_export1, col_export2 = st.columns([1, 3])

    with col_export1:
        if st.button("📥 导出当前页"):
            json_data = json.dumps(current_page_logs, ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ 下载当前页 JSON",
                data=json_data,
                file_name=f"gateway_logs_{selected_date}_page{st.session_state.current_page}.json",
                mime="application/json",
            )

        if st.button("📥 导出全部"):
            json_data = json.dumps(filtered_logs, ensure_ascii=False, indent=2)
            st.download_button(
                label="⬇️ 下载全部 JSON",
                data=json_data,
                file_name=f"gateway_logs_{selected_date}_all.json",
                mime="application/json",
            )

    with col_export2:
        st.caption(
            f"💾 日志存储路径: `{LOG_BASE_DIR / selected_date.strftime('%Y_%m_%d')}`"
        )


# ==================== 主应用 ====================
def main():
    st.sidebar.title("🚀 Micro Gateway")
    st.sidebar.divider()

    # 页面导航
    page = st.sidebar.radio(
        "导航", ["💬 对话", "⚙️ 配置管理", "📊 日志查看"], label_visibility="collapsed"
    )

    # 路由到对应页面
    if page == "💬 对话":
        chat_page()
    elif page == "⚙️ 配置管理":
        config_page()
    elif page == "📊 日志查看":
        logs_page()

    # 侧边栏信息
    st.sidebar.divider()
    st.sidebar.caption(f"网关地址: {GATEWAY_BASE_URL}")
    st.sidebar.caption(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.sidebar.caption(
        f"UTC 时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
    )


if __name__ == "__main__":
    main()
