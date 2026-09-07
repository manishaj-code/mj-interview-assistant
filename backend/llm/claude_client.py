from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from backend.config.schema import LlmConfig

_TOTAL_TIMEOUT_S = 90.0
_GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"
_GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"
_GROQ_MODEL_ALIASES = {
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama-3.1-70b-versatile": "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile": "openai/gpt-oss-20b",
    "llama3-8b-8192": "openai/gpt-oss-20b",
    "llama3-70b-8192": "openai/gpt-oss-20b",
}


class LlmError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def select_transport(
    groq_api_key: str | None,
    gemini_api_key: str | None,
    anthropic_api_key: str | None,
) -> tuple[str, str]:
    if groq_api_key:
        return "groq", groq_api_key
    if gemini_api_key:
        return "gemini", gemini_api_key
    if anthropic_api_key:
        return "anthropic", anthropic_api_key
    return "fake", "x"


def has_llm_key(
    groq_api_key: str | None,
    gemini_api_key: str | None,
    anthropic_api_key: str | None,
) -> bool:
    return bool(groq_api_key or gemini_api_key or anthropic_api_key)


class ClaudeClient:
    def __init__(self, config: LlmConfig, api_key: str, transport: str = "anthropic"):
        self._config = config
        self._api_key = api_key
        self._transport = transport
        self._cancel = asyncio.Event()
        self._client = None
        if transport == "anthropic":
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        elif transport == "groq":
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=api_key)
        elif transport == "gemini":
            from google import genai

            self._client = genai.Client(api_key=api_key)

    def cancel_current(self) -> None:
        self._cancel.set()

    def _model(self) -> str:
        model = self._config.model
        if self._transport == "groq":
            if model in _GROQ_MODEL_ALIASES:
                return _GROQ_MODEL_ALIASES[model]
            if model.startswith(("openai/", "meta-llama/", "qwen/", "groq/")):
                return model
            return _GROQ_DEFAULT_MODEL
        if self._transport == "gemini":
            if "gemini" in model:
                return model
            return _GEMINI_DEFAULT_MODEL
        return model

    async def stream_answer(
        self,
        system: str,
        messages: list[dict],
        timeout_s: float = 30.0,
    ) -> AsyncIterator[str]:
        self._cancel.clear()
        iterator = self._token_iter(system, messages)
        started = asyncio.get_running_loop().time()
        try:
            first = await asyncio.wait_for(anext(iterator), timeout=timeout_s)
        except StopAsyncIteration:
            return
        except TimeoutError as exc:
            raise LlmError("LLM_TIMEOUT", "timed out waiting for first token") from exc
        yield first
        async for token in iterator:
            if asyncio.get_running_loop().time() - started > _TOTAL_TIMEOUT_S:
                raise LlmError("LLM_TIMEOUT", "timed out generating answer")
            if self._cancel.is_set():
                return
            yield token

    async def classify_is_question(self, text: str) -> bool:
        if self._transport in {"fake", "fake_timeout"}:
            lowered = text.casefold()
            return "?" in text or lowered.startswith("what")
        prompt = (
            "Is this a complete interview question that requires an answer? "
            "Reply yes or no only.\n\n"
            f"{text}"
        )
        try:
            if self._transport == "groq":
                kwargs = self._groq_create_kwargs(
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=32,
                    stream=False,
                )
                message = await self._client.chat.completions.create(**kwargs)
                reply = message.choices[0].message.content or ""
            elif self._transport == "gemini":
                message = await self._client.aio.models.generate_content(
                    model=self._model(),
                    contents=prompt,
                )
                reply = getattr(message, "text", None) or ""
            else:
                message = await self._client.messages.create(
                    model=self._model(),
                    max_tokens=20,
                    messages=[{"role": "user", "content": prompt}],
                )
                reply = "".join(block.text for block in message.content if getattr(block, "text", None))
            return "yes" in reply.lower()
        except Exception:
            return False

    async def _token_iter(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        if self._transport == "fake":
            yield "In my "
            yield "previous role."
            return
        if self._transport == "fake_timeout":
            await asyncio.sleep(1)
            yield "late"
            return
        try:
            if self._transport == "groq":
                async for token in self._stream_groq(system, messages):
                    yield token
                return
            if self._transport == "gemini":
                async for token in self._stream_gemini(system, messages):
                    yield token
                return
            async with self._client.messages.stream(
                model=self._model(),
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    if self._cancel.is_set():
                        return
                    if text:
                        yield text
        except LlmError:
            raise
        except Exception as exc:
            raise _llm_error_from_exc(exc) from exc

    def _groq_create_kwargs(self, **extra) -> dict:
        kwargs = {
            "model": self._model(),
            "temperature": self._config.temperature,
            "max_completion_tokens": max(int(self._config.max_tokens), 1024),
        }
        if self._model().startswith("openai/"):
            kwargs["reasoning_effort"] = "low"
            kwargs["include_reasoning"] = False
        kwargs.update(extra)
        return kwargs

    async def _stream_groq(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        payload = [{"role": "system", "content": system}, *messages]
        stream = await self._client.chat.completions.create(
            **self._groq_create_kwargs(messages=payload, stream=True)
        )
        yielded = False
        async for chunk in stream:
            if self._cancel.is_set():
                return
            text = _groq_chunk_text(chunk)
            if text:
                yielded = True
                yield text
        if yielded or self._cancel.is_set():
            return
        completion = await self._client.chat.completions.create(
            **self._groq_create_kwargs(messages=payload, stream=False)
        )
        text = ""
        choices = getattr(completion, "choices", None) or []
        if choices:
            text = getattr(choices[0].message, "content", None) or ""
        if text:
            yield text

    async def _stream_gemini(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        from google.genai import types

        contents = "\n\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model(),
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=self._config.temperature,
                max_output_tokens=self._config.max_tokens,
            ),
        )
        async for chunk in stream:
            if self._cancel.is_set():
                return
            text = getattr(chunk, "text", None)
            if text:
                yield text


def _groq_chunk_text(chunk) -> str:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None) if delta is not None else None
    if isinstance(content, str):
        return content
    return ""


def _llm_error_from_exc(exc: Exception) -> LlmError:
    text = str(exc)
    lower = text.lower()
    if "decommissioned" in lower or "model_decommissioned" in lower:
        return LlmError(
            "LLM_API_ERROR",
            "Groq retired llama-3.1. Restart the app to use openai/gpt-oss-20b.",
        )
    if "credit" in lower or "billing" in lower:
        return LlmError(
            "LLM_BILLING",
            "LLM account has no credits. Use GROQ_API_KEY or GEMINI_API_KEY in .env, then restart.",
        )
    if "429" in lower or "rate limit" in lower or "quota" in lower:
        return LlmError("LLM_API_ERROR", "LLM rate limit or quota exceeded. Try again shortly.")
    return LlmError("LLM_API_ERROR", text)
