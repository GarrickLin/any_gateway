"""测试 parse_stream_usage 函数对三种协议的 SSE 用量解析。"""
import sys
from pathlib import Path

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

from gateway import parse_stream_usage


# ── OpenAI ──────────────────────────────────────────────────────────────────

OPENAI_CHUNKS = [
    'data: {"id":"1","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hi"},"index":0}],"usage":null}\n',
    'data: {"id":"1","object":"chat.completion.chunk","choices":[{"delta":{"content":" there"},"index":0}],"usage":null}\n',
    'data: {"id":"1","object":"chat.completion.chunk","choices":[],"usage":{"prompt_tokens":9,"completion_tokens":12,"total_tokens":21}}\n',
    'data: [DONE]\n',
]


def test_openai_parses_prompt_and_completion_tokens():
    usage = parse_stream_usage(OPENAI_CHUNKS, "openai")
    assert usage.input_tokens == 9
    assert usage.output_tokens == 12
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_openai_ignores_null_usage_chunks():
    chunks = [
        'data: {"choices":[{"delta":{"content":"x"}}],"usage":null}\n',
        'data: [DONE]\n',
    ]
    usage = parse_stream_usage(chunks, "openai")
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


# ── Anthropic ────────────────────────────────────────────────────────────────

ANTHROPIC_CHUNKS = [
    'event: message_start\n',
    'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant","usage":{"input_tokens":15,"output_tokens":0}}}\n',
    '\n',
    'event: content_block_start\n',
    'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n',
    '\n',
    'event: content_block_delta\n',
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n',
    '\n',
    'event: message_delta\n',
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":25}}\n',
    '\n',
    'event: message_stop\n',
    'data: {"type":"message_stop"}\n',
]


def test_anthropic_parses_input_and_output_tokens():
    usage = parse_stream_usage(ANTHROPIC_CHUNKS, "anthropic")
    assert usage.input_tokens == 15
    assert usage.output_tokens == 25
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_anthropic_missing_events_returns_zero():
    chunks = ['data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"x"}}\n']
    usage = parse_stream_usage(chunks, "anthropic")
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


# ── Gemini ───────────────────────────────────────────────────────────────────

GEMINI_CHUNKS = [
    'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":15,"totalTokenCount":25}}\n',
]


def test_gemini_parses_prompt_and_candidates_token_count():
    usage = parse_stream_usage(GEMINI_CHUNKS, "gemini")
    assert usage.input_tokens == 10
    assert usage.output_tokens == 15
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_gemini_takes_last_chunk_when_multiple():
    chunks = [
        'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}],"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":5,"totalTokenCount":15}}\n',
        'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}],"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":15,"totalTokenCount":25}}\n',
    ]
    usage = parse_stream_usage(chunks, "gemini")
    assert usage.input_tokens == 10
    assert usage.output_tokens == 15
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


# ── Fallback ─────────────────────────────────────────────────────────────────

def test_unknown_provider_falls_back_to_openai_format():
    chunks = [
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":8,"total_tokens":13}}\n',
    ]
    usage = parse_stream_usage(chunks, "unknown_provider")
    assert usage.input_tokens == 5
    assert usage.output_tokens == 8
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_empty_provider_falls_back_to_openai_format():
    chunks = [
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":7,"total_tokens":10}}\n',
    ]
    usage = parse_stream_usage(chunks, "")
    assert usage.input_tokens == 3
    assert usage.output_tokens == 7
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


def test_fallback_returns_zero_when_no_usage_found():
    chunks = ['data: {"choices":[{"delta":{"content":"x"}}]}\n', 'data: [DONE]\n']
    usage = parse_stream_usage(chunks, "")
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


# ── Cache Token 解析 ─────────────────────────────────────────────────────────

# Anthropic cache
ANTHROPIC_CACHE_CHUNKS = [
    'event: message_start\n',
    'data: {"type":"message_start","message":{"id":"msg_1","role":"assistant","usage":{"input_tokens":5,"output_tokens":0,"cache_read_input_tokens":800,"cache_creation_input_tokens":100}}}\n',
    '\n',
    'event: message_delta\n',
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":30}}\n',
    '\n',
    'event: message_stop\n',
    'data: {"type":"message_stop"}\n',
]


def test_anthropic_parses_cache_read_tokens():
    usage = parse_stream_usage(ANTHROPIC_CACHE_CHUNKS, "anthropic")
    assert usage.cache_read_tokens == 800


def test_anthropic_parses_cache_creation_tokens():
    usage = parse_stream_usage(ANTHROPIC_CACHE_CHUNKS, "anthropic")
    assert usage.cache_creation_tokens == 100


def test_anthropic_cache_does_not_affect_input_tokens():
    """input_tokens 是非缓存部分，cache 字段是独立的，不应被合并。"""
    usage = parse_stream_usage(ANTHROPIC_CACHE_CHUNKS, "anthropic")
    assert usage.input_tokens == 5


def test_anthropic_no_cache_returns_zero():
    """无缓存时 cache 字段默认为 0。"""
    usage = parse_stream_usage(ANTHROPIC_CHUNKS, "anthropic")
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0


# OpenAI cache
OPENAI_CACHE_CHUNKS = [
    'data: {"choices":[{"delta":{"content":"Hi"}}],"usage":null}\n',
    'data: {"choices":[],"usage":{"prompt_tokens":1000,"completion_tokens":50,"total_tokens":1050,"prompt_tokens_details":{"cached_tokens":800,"audio_tokens":0}}}\n',
    'data: [DONE]\n',
]


def test_openai_parses_cached_tokens_into_cache_read():
    usage = parse_stream_usage(OPENAI_CACHE_CHUNKS, "openai")
    assert usage.cache_read_tokens == 800


def test_openai_cache_creation_is_always_zero():
    """OpenAI 不区分 cache write，cache_creation_tokens 始终为 0。"""
    usage = parse_stream_usage(OPENAI_CACHE_CHUNKS, "openai")
    assert usage.cache_creation_tokens == 0


def test_openai_no_cache_returns_zero():
    """无 prompt_tokens_details 时 cache_read_tokens 为 0。"""
    usage = parse_stream_usage(OPENAI_CHUNKS, "openai")
    assert usage.cache_read_tokens == 0


# Gemini cache
GEMINI_CACHE_CHUNKS = [
    'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":1000,"candidatesTokenCount":50,"totalTokenCount":1050,"cachedContentTokenCount":800}}\n',
]


def test_gemini_parses_cached_content_token_count():
    usage = parse_stream_usage(GEMINI_CACHE_CHUNKS, "gemini")
    assert usage.cache_read_tokens == 800


def test_gemini_cache_creation_is_always_zero():
    usage = parse_stream_usage(GEMINI_CACHE_CHUNKS, "gemini")
    assert usage.cache_creation_tokens == 0


def test_gemini_no_cache_returns_zero():
    usage = parse_stream_usage(GEMINI_CHUNKS, "gemini")
    assert usage.cache_read_tokens == 0


# ── stream_options 注入 ──────────────────────────────────────────────────────

from gateway import inject_stream_options


def test_openai_stream_options_injected_when_missing():
    """OpenAI 流式请求：无 stream_options 时应注入 include_usage=true。"""
    body = {"model": "gpt-4o", "stream": True, "messages": []}
    inject_stream_options(body, "openai")
    assert body["stream_options"] == {"include_usage": True}


def test_openai_stream_options_deep_merged():
    """OpenAI 流式请求：已有其他 stream_options 时只补充 include_usage，不覆盖其他键。"""
    body = {"model": "gpt-4o", "stream": True, "messages": [], "stream_options": {"some_other_option": True}}
    inject_stream_options(body, "openai")
    assert body["stream_options"]["include_usage"] is True
    assert body["stream_options"]["some_other_option"] is True


def test_anthropic_stream_options_not_injected():
    """Anthropic 请求不应注入 stream_options。"""
    body = {"model": "claude-3-5-sonnet", "stream": True, "messages": []}
    inject_stream_options(body, "anthropic")
    assert "stream_options" not in body


def test_gemini_stream_options_not_injected():
    """Gemini 请求不应注入 stream_options。"""
    body = {"model": "gemini-2.0-flash", "stream": True, "contents": []}
    inject_stream_options(body, "gemini")
    assert "stream_options" not in body
