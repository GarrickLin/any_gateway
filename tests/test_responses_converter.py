"""测试 Responses API ↔ Chat Completions 协议转换（方向2：responses→chat）。

纯函数测试，不触碰 DB / 网络。
"""
import sys
from pathlib import Path

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

from services.responses_converter import (
    responses_to_chat_request,
    chat_resp_to_responses_resp,
    chat_stream_to_responses_events,
    format_responses_sse,
)


# ── 请求转换：input → messages ────────────────────────────────────────────────

def test_string_input_becomes_single_user_message():
    chat = responses_to_chat_request({"model": "gpt-4o", "input": "Hello!"})
    assert chat["model"] == "gpt-4o"
    assert chat["messages"] == [{"role": "user", "content": "Hello!"}]


def test_instructions_become_leading_system_message():
    chat = responses_to_chat_request({
        "model": "gpt-4o",
        "instructions": "You are helpful.",
        "input": "Hi",
    })
    assert chat["messages"][0] == {"role": "system", "content": "You are helpful."}
    assert chat["messages"][1] == {"role": "user", "content": "Hi"}


def test_array_input_plain_messages():
    chat = responses_to_chat_request({
        "model": "gpt-4o",
        "input": [
            {"role": "user", "content": "My name is Alice."},
            {"role": "assistant", "content": "Hi Alice!"},
            {"role": "user", "content": "What is my name?"},
        ],
    })
    assert chat["messages"] == [
        {"role": "user", "content": "My name is Alice."},
        {"role": "assistant", "content": "Hi Alice!"},
        {"role": "user", "content": "What is my name?"},
    ]


def test_function_call_output_becomes_tool_message():
    chat = responses_to_chat_request({
        "model": "gpt-4o",
        "input": [
            {"type": "function_call_output", "call_id": "call_1", "output": "{\"temp\": 22}"},
        ],
    })
    assert chat["messages"] == [
        {"role": "tool", "tool_call_id": "call_1", "content": "{\"temp\": 22}"},
    ]


def test_function_call_becomes_assistant_tool_calls():
    chat = responses_to_chat_request({
        "model": "gpt-4o",
        "input": [
            {"type": "function_call", "call_id": "call_1", "name": "get_weather",
             "arguments": "{\"location\":\"Tokyo\"}"},
        ],
    })
    msg = chat["messages"][0]
    assert msg["role"] == "assistant"
    assert msg["tool_calls"] == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"location\":\"Tokyo\"}"},
    }]


# ── Vision ────────────────────────────────────────────────────────────────────

def test_input_image_converts_to_image_url():
    chat = responses_to_chat_request({
        "model": "gpt-4o",
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What is this?"},
                {"type": "input_image", "image_url": "https://x/p.jpg", "detail": "high"},
            ],
        }],
    })
    content = chat["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://x/p.jpg", "detail": "high"},
    }


# ── 参数映射 ──────────────────────────────────────────────────────────────────

def test_max_output_tokens_maps_to_max_completion_tokens():
    chat = responses_to_chat_request({"model": "m", "input": "x", "max_output_tokens": 100})
    assert chat["max_completion_tokens"] == 100


def test_reasoning_effort_maps():
    chat = responses_to_chat_request({
        "model": "o3", "input": "x", "reasoning": {"effort": "high"}})
    assert chat["reasoning_effort"] == "high"


def test_text_format_json_schema_maps_to_response_format():
    chat = responses_to_chat_request({
        "model": "m", "input": "x",
        "text": {"format": {
            "type": "json_schema", "name": "person", "strict": True,
            "schema": {"type": "object", "properties": {"n": {"type": "string"}}},
        }},
    })
    rf = chat["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "person"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["type"] == "object"


def test_simple_params_pass_through():
    chat = responses_to_chat_request({
        "model": "m", "input": "x",
        "temperature": 0.5, "top_p": 0.9, "tool_choice": "auto",
        "parallel_tool_calls": True, "user": "u1",
    })
    assert chat["temperature"] == 0.5
    assert chat["top_p"] == 0.9
    assert chat["tool_choice"] == "auto"
    assert chat["parallel_tool_calls"] is True
    assert chat["user"] == "u1"


# ── Tools ─────────────────────────────────────────────────────────────────────

def test_function_tool_is_wrapped():
    chat = responses_to_chat_request({
        "model": "m", "input": "x",
        "tools": [{
            "type": "function", "name": "get_weather",
            "description": "Get weather",
            "parameters": {"type": "object", "properties": {"loc": {"type": "string"}}},
        }],
    })
    assert chat["tools"] == [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {"type": "object", "properties": {"loc": {"type": "string"}}},
        },
    }]


def test_non_function_tools_are_skipped():
    chat = responses_to_chat_request({
        "model": "m", "input": "x",
        "tools": [
            {"type": "web_search"},
            {"type": "function", "name": "f"},
        ],
    })
    assert len(chat["tools"]) == 1
    assert chat["tools"][0]["function"]["name"] == "f"


# ── stream_options 注入 ───────────────────────────────────────────────────────

def test_stream_injects_include_usage():
    chat = responses_to_chat_request({"model": "m", "input": "x", "stream": True})
    assert chat["stream"] is True
    assert chat["stream_options"] == {"include_usage": True}


def test_non_stream_has_no_stream_options():
    chat = responses_to_chat_request({"model": "m", "input": "x"})
    assert "stream_options" not in chat


# ── 非流式响应转换：chat → responses ──────────────────────────────────────────

def _chat_resp(message: dict, finish_reason: str = "stop", usage: dict | None = None):
    resp = {
        "id": "chatcmpl-abc",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }
    if usage is not None:
        resp["usage"] = usage
    return resp


def test_text_response_becomes_message_output_item():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": "Hello there!"}))
    assert out["object"] == "response"
    assert out["status"] == "completed"
    assert out["model"] == "gpt-4o"
    item = out["output"][0]
    assert item["type"] == "message"
    assert item["role"] == "assistant"
    assert item["content"][0] == {
        "type": "output_text", "text": "Hello there!", "annotations": []}


def test_id_prefix_converted_to_resp():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": "x"}))
    assert out["id"] == "resp_abc"


def test_tool_calls_become_function_call_items():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "get_weather", "arguments": "{\"loc\":\"Tokyo\"}"},
        }]},
        finish_reason="tool_calls",
    ))
    fc = [i for i in out["output"] if i["type"] == "function_call"]
    assert len(fc) == 1
    assert fc[0]["name"] == "get_weather"
    assert fc[0]["arguments"] == "{\"loc\":\"Tokyo\"}"
    assert fc[0]["call_id"] == "call_1"


def test_refusal_becomes_refusal_part():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": None, "refusal": "I cannot help."}))
    item = out["output"][0]
    assert item["content"][0]["type"] == "refusal"
    assert item["content"][0]["refusal"] == "I cannot help."


def test_finish_reason_length_marks_incomplete():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": "trunc"}, finish_reason="length"))
    assert out["status"] == "incomplete"
    assert out["incomplete_details"]["reason"] == "max_output_tokens"


def test_usage_maps_to_input_output_tokens():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": "x"},
        usage={"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    ))
    assert out["usage"]["input_tokens"] == 20
    assert out["usage"]["output_tokens"] == 8
    assert out["usage"]["total_tokens"] == 28


def test_usage_details_reasoning_and_cached():
    out = chat_resp_to_responses_resp(_chat_resp(
        {"role": "assistant", "content": "x"},
        usage={
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            "completion_tokens_details": {"reasoning_tokens": 30},
            "prompt_tokens_details": {"cached_tokens": 80},
        },
    ))
    assert out["usage"]["output_tokens_details"]["reasoning_tokens"] == 30
    assert out["usage"]["input_tokens_details"]["cached_tokens"] == 80


# ── 流式响应转换：chat SSE → responses 事件 ───────────────────────────────────

_STREAM_KW = {"model": "gpt-4o", "response_id": "resp_x", "msg_id": "msg_x",
              "created": 1700000000}


def _events(chat_chunks):
    """收集生成器产出的 (event_type, data) 元组列表。"""
    return list(chat_stream_to_responses_events(iter(chat_chunks), **_STREAM_KW))


def _types(events):
    return [t for t, _ in events]


def test_text_stream_event_sequence():
    chunks = [
        {"choices": [{"delta": {"role": "assistant", "content": "Hello"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": " world"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
    ]
    types = _types(_events(chunks))
    # 必须以 created/in_progress 开头
    assert types[0] == "response.created"
    assert types[1] == "response.in_progress"
    assert "response.output_item.added" in types
    assert "response.content_part.added" in types
    # 两段文本 delta
    assert types.count("response.output_text.delta") == 2
    # 收尾事件
    assert "response.output_text.done" in types
    assert "response.content_part.done" in types
    assert "response.output_item.done" in types
    # 以 completed 结尾
    assert types[-1] == "response.completed"


def test_text_stream_delta_payload():
    chunks = [
        {"choices": [{"delta": {"content": "Hi"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = _events(chunks)
    deltas = [d["delta"] for t, d in events if t == "response.output_text.delta"]
    assert deltas == ["Hi"]


def test_sequence_numbers_are_monotonic():
    chunks = [
        {"choices": [{"delta": {"content": "a"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    events = _events(chunks)
    seqs = [d["sequence_number"] for _, d in events]
    assert seqs == list(range(len(seqs)))


def test_completed_event_carries_usage():
    chunks = [
        {"choices": [{"delta": {"content": "x"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}},
    ]
    events = _events(chunks)
    completed = [d for t, d in events if t == "response.completed"][0]
    usage = completed["response"]["usage"]
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 4


def test_finish_reason_length_marks_incomplete_status():
    chunks = [
        {"choices": [{"delta": {"content": "x"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    ]
    events = _events(chunks)
    completed = [d for t, d in events if t == "response.completed"][0]
    assert completed["response"]["status"] == "incomplete"


def test_tool_call_stream_emits_function_call_events():
    chunks = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_1", "type": "function",
            "function": {"name": "get_weather", "arguments": ""}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": "{\"loc\":"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": "\"Tokyo\"}"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    events = _events(chunks)
    types = _types(events)
    # 首次出现工具调用 → output_item.added(function_call)
    added = [d for t, d in events if t == "response.output_item.added"
             and d["item"].get("type") == "function_call"]
    assert len(added) == 1
    assert added[0]["item"]["name"] == "get_weather"
    # 参数 delta 累积
    arg_deltas = [d["delta"] for t, d in events
                  if t == "response.function_call_arguments.delta"]
    assert "".join(arg_deltas) == "{\"loc\":\"Tokyo\"}"
    assert "response.function_call_arguments.done" in types
    assert types[-1] == "response.completed"


def test_format_responses_sse_shape():
    s = format_responses_sse("response.created", {"type": "response.created", "a": 1})
    assert s.startswith("event: response.created\n")
    assert "data: " in s
    assert s.endswith("\n\n")
