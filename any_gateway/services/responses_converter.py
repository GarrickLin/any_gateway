"""Responses API ↔ Chat Completions 协议转换（方向2：responses→chat）。

网关上游全部是 Chat Completions API。本模块把对外的 Responses 请求翻译成
Chat Completions 请求发给上游，再把上游的 Chat Completions 响应翻译回 Responses
格式返回给客户端（如 codex）。

设计文档：docs/plans/2026-06-12-responses-api-design.md
参考实现：docs/refs/open-ai-converter（Go 双向转换代理的「方向2」）

纯函数模块：无副作用、无 I/O。
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterator


def _convert_id(raw: str | None, prefix: str) -> str:
    """转换 id 前缀，如 chatcmpl-abc → resp_abc。"""
    if not raw:
        return f"{prefix}{int(time.time() * 1e9)}"
    if raw.startswith(prefix):
        return raw
    for p in ("chatcmpl-", "resp_", "cmpl-"):
        if raw.startswith(p):
            return prefix + raw[len(p):]
    return prefix + raw


# ── Vision 内容转换 ───────────────────────────────────────────────────────────

def _convert_content(content: Any) -> Any:
    """Responses content（字符串或多模态数组）→ Chat Completions content。

    input_text → text，input_image → image_url:{url, detail}。
    其余类型原样透传。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return content

    result: list[dict] = []
    for part in content:
        if not isinstance(part, dict):
            result.append(part)
            continue
        ptype = part.get("type")
        if ptype in ("input_text", "text"):
            result.append({"type": "text", "text": part.get("text", "")})
        elif ptype == "input_image":
            image_url: dict[str, Any] = {"url": part.get("image_url", "")}
            if part.get("detail"):
                image_url["detail"] = part["detail"]
            result.append({"type": "image_url", "image_url": image_url})
        else:
            result.append(part)
    return result


# ── Structured Output 转换 ────────────────────────────────────────────────────

def _convert_text_format(text: dict) -> Any:
    """Responses text.format → Chat Completions response_format。"""
    fmt = text.get("format")
    if not isinstance(fmt, dict):
        return None
    ftype = fmt.get("type")
    if ftype == "json_object":
        return {"type": "json_object"}
    if ftype == "json_schema":
        js: dict[str, Any] = {"name": fmt.get("name")}
        if fmt.get("description"):
            js["description"] = fmt["description"]
        if fmt.get("schema") is not None:
            js["schema"] = fmt["schema"]
        if fmt.get("strict") is not None:
            js["strict"] = fmt["strict"]
        return {"type": "json_schema", "json_schema": js}
    if ftype == "text":
        return {"type": "text"}
    return {"type": ftype}


# ── 请求转换：responses → chat ────────────────────────────────────────────────

def responses_to_chat_request(body: dict) -> dict:
    """Responses 请求体 → Chat Completions 请求体。

    移植 Go converter 的 ConvertResponsesToChatRequest。
    """
    chat: dict[str, Any] = {"model": body.get("model")}
    if body.get("stream"):
        chat["stream"] = True

    messages: list[dict] = []

    # instructions → 开头的 system 消息
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    # input：字符串 or 数组
    raw_input = body.get("input")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id"),
                    "content": item.get("output"),
                })
            elif itype == "function_call":
                messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": item.get("call_id"),
                        "type": "function",
                        "function": {
                            "name": item.get("name"),
                            "arguments": item.get("arguments"),
                        },
                    }],
                })
            else:
                m: dict[str, Any] = {"role": item.get("role")}
                if "content" in item:
                    m["content"] = _convert_content(item.get("content"))
                messages.append(m)

    chat["messages"] = messages

    # ---- 参数映射 ----
    if body.get("max_output_tokens") is not None:
        chat["max_completion_tokens"] = body["max_output_tokens"]
    for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty",
                "store", "metadata", "service_tier", "parallel_tool_calls",
                "tool_choice", "user"):
        if body.get(key) is not None:
            chat[key] = body[key]

    # top_logprobs → logprobs + top_logprobs
    if body.get("top_logprobs") is not None and body["top_logprobs"] > 0:
        chat["logprobs"] = True
        chat["top_logprobs"] = body["top_logprobs"]

    # reasoning.effort → reasoning_effort
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("effort"):
        chat["reasoning_effort"] = reasoning["effort"]

    # text.format → response_format
    if isinstance(body.get("text"), dict):
        rf = _convert_text_format(body["text"])
        if rf is not None:
            chat["response_format"] = rf

    # tools：仅保留 function 类型，其余（web_search 等）静默跳过
    tools = body.get("tools")
    if isinstance(tools, list):
        chat_tools: list[dict] = []
        for t in tools:
            if not isinstance(t, dict) or t.get("type") != "function":
                continue
            fn: dict[str, Any] = {"name": t.get("name")}
            if t.get("description"):
                fn["description"] = t["description"]
            if t.get("parameters") is not None:
                fn["parameters"] = t["parameters"]
            if t.get("strict") is not None:
                fn["strict"] = t["strict"]
            chat_tools.append({"type": "function", "function": fn})
        if chat_tools:
            chat["tools"] = chat_tools

    # stream → 注入 stream_options.include_usage（计费拿 token 的前提）
    if body.get("stream"):
        chat["stream_options"] = {"include_usage": True}

    return chat


# ── 非流式响应转换：chat → responses ──────────────────────────────────────────

def _content_to_str(content: Any) -> str:
    """Chat message.content（字符串 / 多模态数组 / null）→ 纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and "text" in p:
                parts.append(p["text"])
        return "".join(parts)
    return str(content)


def _convert_usage(usage: dict) -> dict:
    """Chat usage → Responses usage（含 reasoning / cached 明细）。"""
    out: dict[str, Any] = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    ctd = usage.get("completion_tokens_details")
    if isinstance(ctd, dict):
        out["output_tokens_details"] = {
            "reasoning_tokens": ctd.get("reasoning_tokens", 0)}
    ptd = usage.get("prompt_tokens_details")
    if isinstance(ptd, dict):
        out["input_tokens_details"] = {"cached_tokens": ptd.get("cached_tokens", 0)}
    return out


def chat_resp_to_responses_resp(chat: dict) -> dict:
    """非流式 Chat Completions 响应 → Responses 响应。

    移植 Go converter 的 ConvertChatRespToResponsesResp。
    """
    resp: dict[str, Any] = {
        "id": _convert_id(chat.get("id"), "resp_"),
        "object": "response",
        "created_at": chat.get("created"),
        "status": "completed",
        "model": chat.get("model"),
        "output": [],
    }
    if chat.get("service_tier") is not None:
        resp["service_tier"] = chat["service_tier"]

    for choice in chat.get("choices", []):
        msg = choice.get("message")
        if not msg:
            continue

        if choice.get("finish_reason") == "length":
            resp["status"] = "incomplete"
            resp["incomplete_details"] = {"reason": "max_output_tokens"}

        tool_calls = msg.get("tool_calls") or []

        # message output item（有文本/refusal 或无工具调用时）
        if msg.get("content") is not None or not tool_calls:
            refusal = msg.get("refusal")
            if refusal:
                content_part = {"type": "refusal", "refusal": refusal}
            else:
                content_part = {
                    "type": "output_text",
                    "text": _content_to_str(msg.get("content")),
                    "annotations": [],
                }
            resp["output"].append({
                "id": f"msg_{int(time.time() * 1e9)}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [content_part],
            })

        # function_call output items
        for tc in tool_calls:
            fn = tc.get("function", {})
            resp["output"].append({
                "id": tc.get("id"),
                "type": "function_call",
                "status": "completed",
                "name": fn.get("name"),
                "arguments": fn.get("arguments"),
                "call_id": tc.get("id"),
            })

    usage = chat.get("usage")
    if isinstance(usage, dict):
        resp["usage"] = _convert_usage(usage)

    return resp


# ── 流式响应转换：chat SSE → responses 事件 ───────────────────────────────────

def format_responses_sse(event_type: str, data: dict) -> str:
    """把 (event_type, data) 格式化为 Responses SSE 文本块。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class _ResponsesStreamState:
    """Responses 流式转换状态机：header() → feed(chunk)* → finalize()。

    设计为可逐 chunk 增量驱动：上游是 async 流（aiter_lines），同步生成器无法
    await，故拆成三段供 async 端点调用。移植 Go converter 的
    handleResponsesStreamViaChat。
    """

    def __init__(self, *, model: str | None, response_id: str, msg_id: str,
                 created: int | None):
        self.model = model
        self.response_id = response_id
        self.msg_id = msg_id
        self.created = created
        self.seq = 0
        self.full_text: list[str] = []
        self.usage: dict | None = None
        self.tool_calls: dict[int, dict] = {}  # index → {id, name, arguments}
        self.finish_reason = "stop"

    def _make(self, event_type: str, data: dict) -> tuple[str, dict]:
        data["sequence_number"] = self.seq
        self.seq += 1
        return (event_type, data)

    def header(self) -> list[tuple[str, dict]]:
        """流开始时的固定前导事件（4 条）。"""
        base = {
            "id": self.response_id, "object": "response", "created_at": self.created,
            "status": "in_progress", "model": self.model, "output": [],
        }
        return [
            self._make("response.created",
                       {"type": "response.created", "response": base}),
            self._make("response.in_progress",
                       {"type": "response.in_progress", "response": base}),
            self._make("response.output_item.added", {
                "type": "response.output_item.added", "output_index": 0,
                "item": {"id": self.msg_id, "type": "message", "status": "in_progress",
                         "content": [], "role": "assistant"}}),
            self._make("response.content_part.added", {
                "type": "response.content_part.added", "content_index": 0,
                "item_id": self.msg_id, "output_index": 0,
                "part": {"type": "output_text", "annotations": [], "text": ""}}),
        ]

    def feed(self, chunk: dict) -> list[tuple[str, dict]]:
        """处理一个上游 chat chunk，返回 0+ 个 responses 事件。"""
        events: list[tuple[str, dict]] = []
        if not isinstance(chunk, dict):
            return events
        if isinstance(chunk.get("usage"), dict):
            self.usage = chunk["usage"]

        choices = chunk.get("choices") or []
        if not choices:
            return events
        choice = choices[0]
        delta = choice.get("delta") or {}

        content = delta.get("content")
        if content:
            self.full_text.append(content)
            events.append(self._make("response.output_text.delta", {
                "type": "response.output_text.delta", "content_index": 0,
                "item_id": self.msg_id, "output_index": 0, "delta": content}))

        refusal = delta.get("refusal")
        if refusal:
            events.append(self._make("response.refusal.delta", {
                "type": "response.refusal.delta", "content_index": 0,
                "item_id": self.msg_id, "output_index": 0, "delta": refusal}))

        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            fn = tc.get("function") or {}
            arg = fn.get("arguments") or ""
            if idx not in self.tool_calls:
                tc_id = tc.get("id")
                self.tool_calls[idx] = {
                    "id": tc_id, "name": fn.get("name"), "arguments": arg}
                events.append(self._make("response.output_item.added", {
                    "type": "response.output_item.added", "output_index": idx + 1,
                    "item": {"id": tc_id, "type": "function_call", "status": "in_progress",
                             "call_id": tc_id, "name": fn.get("name"), "arguments": ""}}))
                if arg:
                    events.append(self._make("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": tc_id, "output_index": idx + 1, "delta": arg}))
            else:
                existing = self.tool_calls[idx]
                existing["arguments"] += arg
                if arg:
                    events.append(self._make("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": existing["id"], "output_index": idx + 1, "delta": arg}))

        # 记录 finish_reason 但不中断：OpenAI 常把 usage 放在 finish 之后的独立 chunk
        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]
        return events

    def finalize(self) -> list[tuple[str, dict]]:
        """流结束时的收尾事件（工具调用收尾 + message 收尾 + completed）。"""
        events: list[tuple[str, dict]] = []
        for idx, tc in self.tool_calls.items():
            events.append(self._make("response.function_call_arguments.done", {
                "type": "response.function_call_arguments.done",
                "item_id": tc["id"], "output_index": idx + 1, "arguments": tc["arguments"]}))
            events.append(self._make("response.output_item.done", {
                "type": "response.output_item.done", "output_index": idx + 1,
                "item": {"id": tc["id"], "type": "function_call", "status": "completed",
                         "call_id": tc["id"], "name": tc["name"],
                         "arguments": tc["arguments"]}}))

        text = "".join(self.full_text)
        events.append(self._make("response.output_text.done", {
            "type": "response.output_text.done", "content_index": 0,
            "item_id": self.msg_id, "output_index": 0, "text": text}))
        events.append(self._make("response.content_part.done", {
            "type": "response.content_part.done", "content_index": 0,
            "item_id": self.msg_id, "output_index": 0,
            "part": {"type": "output_text", "annotations": [], "text": text}}))
        events.append(self._make("response.output_item.done", {
            "type": "response.output_item.done", "output_index": 0,
            "item": {"id": self.msg_id, "type": "message", "status": "completed",
                     "role": "assistant",
                     "content": [{"type": "output_text", "annotations": [], "text": text}]}}))

        output_items: list[dict] = [{
            "id": self.msg_id, "type": "message", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "annotations": [], "text": text}]}]
        for idx, tc in self.tool_calls.items():
            output_items.append({
                "id": tc["id"], "type": "function_call", "status": "completed",
                "call_id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]})

        final_status = "incomplete" if self.finish_reason == "length" else "completed"
        completed: dict[str, Any] = {
            "id": self.response_id, "object": "response", "created_at": self.created,
            "status": final_status, "model": self.model, "output": output_items}
        if self.usage is not None:
            completed["usage"] = _convert_usage(self.usage)
        events.append(self._make("response.completed", {
            "type": "response.completed", "response": completed}))
        return events


def chat_stream_to_responses_events(
    chat_chunks: Iterator[dict],
    *,
    model: str | None,
    response_id: str,
    msg_id: str,
    created: int | None,
) -> Iterator[tuple[str, dict]]:
    """把已解析的 chat chunk 迭代器整体转为 responses 事件流（薄包装，便于测试）。

    端点侧的真流式逐 chunk 驱动直接使用 _ResponsesStreamState 的
    header()/feed()/finalize()。
    """
    state = _ResponsesStreamState(
        model=model, response_id=response_id, msg_id=msg_id, created=created)
    yield from state.header()
    for chunk in chat_chunks:
        yield from state.feed(chunk)
    yield from state.finalize()
