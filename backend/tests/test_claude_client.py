import pytest

from backend.config.schema import LlmConfig
from backend.llm.claude_client import ClaudeClient, LlmError, _groq_chunk_text, _llm_error_from_exc, select_transport

CFG = LlmConfig(model="claude-sonnet-4-6", max_tokens=50, temperature=0.4, answer_style="concise")


@pytest.mark.asyncio
async def test_stream_yields_deltas():
    client = ClaudeClient(CFG, api_key="x", transport="fake")
    tokens = []
    async for t in client.stream_answer("sys", [{"role": "user", "content": "hi"}]):
        tokens.append(t)
    assert tokens == ["In my ", "previous role."]


@pytest.mark.asyncio
async def test_timeout_raises():
    client = ClaudeClient(CFG, api_key="x", transport="fake_timeout")
    with pytest.raises(LlmError) as ei:
        async for _ in client.stream_answer("sys", [{"role": "user", "content": "hi"}], timeout_s=0.01):
            pass
    assert ei.value.code == "LLM_TIMEOUT"


@pytest.mark.asyncio
async def test_classify_true():
    client = ClaudeClient(CFG, api_key="x", transport="fake")
    assert await client.classify_is_question("What is Redis?") is True


def test_maps_credit_error():
    err = _llm_error_from_exc(Exception("Your credit balance is too low"))
    assert err.code == "LLM_BILLING"
    assert "credits" in err.message.lower() or "groq" in err.message.lower()


def test_select_transport_prefers_groq():
    transport, key = select_transport("gsk-x", "gemini-x", "sk-ant-x")
    assert transport == "groq"
    assert key == "gsk-x"


def test_select_transport_gemini_next():
    transport, key = select_transport(None, "gemini-x", "sk-ant-x")
    assert transport == "gemini"
    assert key == "gemini-x"


def test_groq_uses_default_model_when_claude_configured():
    client = ClaudeClient(CFG, api_key="x", transport="fake")
    client._transport = "groq"
    assert client._model() == "openai/gpt-oss-20b"
    client._transport = "gemini"
    assert client._model() == "gemini-2.0-flash"


def test_groq_maps_retired_llama31():
    cfg = LlmConfig(model="llama-3.1-8b-instant", max_tokens=50, temperature=0.4, answer_style="concise")
    client = ClaudeClient(cfg, api_key="x", transport="fake")
    client._transport = "groq"
    assert client._model() == "openai/gpt-oss-20b"


def test_maps_decommissioned_model():
    err = _llm_error_from_exc(Exception("The model `llama-3.1-8b-instant` has been decommissioned."))
    assert err.code == "LLM_API_ERROR"
    assert "retired" in err.message.lower() or "gpt-oss" in err.message.lower()


def test_groq_chunk_text_reads_delta_content():
    class Delta:
        content = "Hello"

    class Choice:
        delta = Delta()

    class Chunk:
        choices = [Choice()]

    assert _groq_chunk_text(Chunk()) == "Hello"
