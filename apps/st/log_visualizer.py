import streamlit as st
from st_copy import copy_button
from loguru import logger
import json
import re


# 定义正则表达式
# re.MULTILINE (或 re.M) 不是必需的，但如果数据跨越多行，它会很有用
regex_pattern = r"event: (?P<event>\w+)\s+data:\s*(?P<data>\{.*\})"


def vis_request(request):
    if isinstance(request, str):
        try:
            request = json.loads(request)
        except json.JSONDecodeError as e:
            st.write(f"Invalid JSON: {e}")
    if isinstance(request, dict):
        msg = request.get("messages", [{}])[-1]
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                st.markdown(content)
            else:
                st.write(content)
        # if isinstance(content, list) and content:
        #     st.markdown(content[-1].get("text", ""))
        # elif isinstance(content, str):
        #     st.markdown(content)


@st.cache_data
def collect_events(text):
    # 存储提取结果的列表
    extracted_data = []

    # 查找所有匹配项
    # re.finditer 会返回一个迭代器，包含所有匹配的对象
    for match in re.finditer(regex_pattern, text):
        # 从匹配对象中通过名称获取捕获组
        event_name = match.group("event")
        data_json_str = match.group("data")

        # 尝试将 JSON 字符串解析为 Python 字典
        try:
            data_dict = json.loads(data_json_str)
        except json.JSONDecodeError:
            # 如果 JSON 格式有误，则按原样保留字符串
            data_dict = data_json_str

        # 将提取的信息添加到列表中
        extracted_data.append({"event": event_name, "data": data_dict})

    # --- 打印结果 ---
    logger.info(f"成功提取到 {len(extracted_data)} 条 Anthropic 事件。")

    return extracted_data


def collect_openai_events(text):
    """解析 OpenAI SSE 格式 (仅 data: 前缀)"""
    extracted_data = []

    # OpenAI SSE 格式: 每行一个 data: {json}
    # 按行处理更可靠
    for line in text.split("\n"):
        line = line.strip()
        if not line or line == "data: [DONE]":
            continue

        if line.startswith("data:"):
            json_str = line[5:].strip()  # 移除 "data:" 前缀
            try:
                data_dict = json.loads(json_str)
                # OpenAI 格式统一标记为 "message" 事件
                extracted_data.append({"event": "message", "data": data_dict})
            except json.JSONDecodeError:
                # 忽略解析失败的数据
                continue

    logger.info(f"成功提取到 {len(extracted_data)} 条 OpenAI 事件。")
    return extracted_data


def vis_response(response):
    try:
        response = json.loads(response)
        st.write(response)
    except json.JSONDecodeError as e:
        # 检测 SSE 格式类型
        is_anthropic = response.startswith("event:")
        is_openai = not is_anthropic and "data:" in response

        # 根据格式解析事件
        if is_anthropic:
            events = collect_events(response)
            _render_anthropic_events(events)
        elif is_openai:
            events = collect_openai_events(response)
            _render_openai_events(events)
        else:
            st.error("未识别的 SSE 格式")


def _render_anthropic_events(events):
    """渲染 Anthropic SSE 格式的事件"""
    # 使用字典按 index 分组存储内容块
    content_blocks = {}

    for event in events:
        if isinstance(event["data"], dict):
            data_type = event["data"].get("type")
            index = event["data"].get("index")

            if data_type == "content_block_start":
                # 初始化该 index 的内容块
                if index not in content_blocks:
                    content_blocks[index] = {
                        "type": None,
                        "tool": None,
                        "text": [],
                        "input_json": [],
                    }

                block_type = event["data"].get("content_block", {}).get("type")
                content_blocks[index]["type"] = block_type

                if block_type == "text":
                    text = event["data"].get("content_block", {}).get("text", "")
                    content_blocks[index]["text"].append(text)
                elif block_type == "tool_use":
                    content_blocks[index]["tool"] = event["data"].get(
                        "content_block", {}
                    )

            elif data_type == "content_block_delta":
                # 确保该 index 已初始化
                if index not in content_blocks:
                    content_blocks[index] = {
                        "type": None,
                        "tool": None,
                        "text": [],
                        "input_json": [],
                    }

                delta_type = event["data"].get("delta", {}).get("type")
                if delta_type == "text_delta":
                    text = event["data"].get("delta", {}).get("text", None)
                    if text is not None:
                        content_blocks[index]["text"].append(text)
                elif delta_type == "input_json_delta":
                    partial_json = (
                        event["data"].get("delta", {}).get("partial_json", None)
                    )
                    if partial_json is not None:
                        content_blocks[index]["input_json"].append(partial_json)

    # 按 index 顺序显示内容
    for index in sorted(content_blocks.keys()):
        block = content_blocks[index]

        if block["text"]:
            text_to_view = "".join(block["text"])
            st.write(text_to_view)
            copy_button(
                text_to_view,
                tooltip="Copy",
                copied_label="Copied!",
                icon="st",
            )

        if block["tool"]:
            tool = block["tool"]
            if block["input_json"]:
                input_json_str = "".join(block["input_json"])
                try:
                    if isinstance(tool.get("input"), str):
                        tool["input"] += input_json_str
                    else:
                        tool["input"] = input_json_str

                    tool["input"] = json.loads(tool["input"])
                    st.write(tool)
                except json.JSONDecodeError:
                    st.write(tool)
                    st.write("".join(block["input_json"]))
            else:
                st.write(tool)


def _render_openai_events(events):
    """渲染 OpenAI SSE 格式的事件"""
    text_parts = []

    for event in events:
        if isinstance(event["data"], dict):
            choices = event["data"].get("choices", [])
            for choice in choices:
                delta = choice.get("delta", {})

                # 提取 role (仅在第一次出现)
                role = delta.get("role")
                if role:
                    st.write(f"**Role:** {role}")

                # 提取增量内容
                content = delta.get("content")
                if content:
                    text_parts.append(content)

                # 检查是否结束
                finish_reason = choice.get("finish_reason")
                if finish_reason:
                    logger.info(f"Stream finished: {finish_reason}")

    # 显示完整文本
    if text_parts:
        full_text = "".join(text_parts)
        st.markdown(full_text)
        copy_button(
            full_text,
            tooltip="Copy",
            copied_label="Copied!",
            icon="st",
        )
