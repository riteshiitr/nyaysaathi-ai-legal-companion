"""The only module that talks to an AI provider.

The rest of the app calls complete() and transcribe() on an LLMProvider. Most
services only need settings in .env (see PROVIDERS in config.py). A service with a
different API needs one new class with those two methods, registered in
get_provider(). Nothing else has to change.
"""

import base64
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import openai

from config import Settings

RATE_LIMIT_WAIT_SECONDS = 65


class AIError(Exception):
    """A provider failure, with a message that is safe to show the user."""

    def __init__(self, kind: str, user_message: str):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    is_mock: bool = False


class LLMProvider(Protocol):
    def complete(
        self,
        system: str,
        messages: list[dict],
        schema: dict | None = None,
        schema_name: str = "response",
        fast: bool = False,
    ) -> LLMResponse: ...

    def transcribe(self, audio: bytes, filename: str, language: str | None = None) -> str: ...


def _make_client(settings: Settings) -> openai.OpenAI:
    if not settings.has_api_key:
        raise AIError(
            "no_key",
            f"No API key is configured for {settings.provider_label}. "
            f"Add {settings.key_name} to your settings. See the README for setup steps.",
        )
    return openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=180.0, max_retries=2)


class ChatCompatibleProvider:
    """Any service with an OpenAI-style Chat Completions API, including Google Gemini."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = _make_client(settings)

    def _send(self, request: dict) -> LLMResponse:
        try:
            response = self._client.chat.completions.create(**request)
        except Exception as error:
            raise _to_ai_error(error, self._settings) from error

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise AIError("incomplete", "The AI's answer was cut off (length). Please try again.")
        if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
            raise AIError("refusal", "The AI declined this request. Please rephrase it or consult a lawyer.")
        if not choice.message.content:
            raise AIError("failed", "The AI service returned an empty answer. Please try again.")

        usage = response.usage
        return LLMResponse(
            text=choice.message.content,
            model=response.model or request["model"],
            provider=self._settings.provider,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    def complete(self, system, messages, schema=None, schema_name="response", fast=False) -> LLMResponse:
        request = {
            "model": self._settings.fast_model if fast else self._settings.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": self._settings.max_tokens,
        }
        if self._settings.effort != "default":
            request["reasoning_effort"] = self._settings.effort
        if schema:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        return self._send(request)

    def transcribe(self, audio, filename, language=None) -> str:
        """Gemini has no separate speech-to-text route here, so audio goes in a normal chat message."""
        instruction = "Transcribe this audio exactly. Return only the words that were spoken."
        if language:
            instruction += f" The speaker's language code is {language}."
        audio_format = filename.rsplit(".", 1)[-1].lower()
        request = {
            "model": self._settings.transcribe_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": audio_format},
                        },
                    ],
                }
            ],
            "max_tokens": self._settings.max_tokens,
        }
        return self._send(request).text.strip()


class OpenAIProvider:
    """Calls the OpenAI Responses API. store=False asks OpenAI not to keep the response."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = _make_client(settings)

    def complete(self, system, messages, schema=None, schema_name="response", fast=False) -> LLMResponse:
        model = self._settings.fast_model if fast else self._settings.model
        request = {
            "model": model,
            "instructions": system,
            "input": messages,
            "max_output_tokens": self._settings.max_tokens,
            "store": False,
        }
        if self._settings.effort != "default":
            request["reasoning"] = {"effort": self._settings.effort}
        if schema:
            request["text"] = {
                "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}
            }
        try:
            response = self._client.responses.create(**request)
        except Exception as error:
            raise _to_ai_error(error, self._settings) from error

        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
            raise AIError("incomplete", f"The AI's answer was cut off ({reason}). Please try again.")
        if response.status == "failed":
            raise AIError("failed", "The AI service could not complete this request. Please try again.")

        for item in response.output:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", "") == "refusal":
                    raise AIError("refusal", "The AI declined this request. Please rephrase it or consult a lawyer.")

        usage = response.usage
        return LLMResponse(
            text=response.output_text,
            model=response.model,
            provider="openai",
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )

    def transcribe(self, audio, filename, language=None) -> str:
        request = {"model": self._settings.transcribe_model, "file": (filename, audio)}
        if language:
            request["language"] = language
        try:
            return self._client.audio.transcriptions.create(**request).text
        except Exception as error:
            raise _to_ai_error(error, self._settings) from error


def _to_ai_error(error: Exception, settings: Settings) -> AIError:
    """Turn an SDK error into plain instructions. The API key never appears in these messages."""
    label = settings.provider_label
    if isinstance(error, openai.RateLimitError):
        detail = str(error).lower()
        if settings.provider == "openai" and ("insufficient_quota" in detail or "no credits" in detail or "quota" in detail):
            return AIError(
                "no_credit",
                "The OpenAI account behind this app has no credit left, so the AI cannot answer. "
                "Credit can be added at platform.openai.com/settings/organization/billing.",
            )
        # Free tiers report per-minute and per-day limits with the same error code.
        if "perday" in detail or "per day" in detail or "per_day" in detail:
            return AIError("daily_limit", f"The daily limit for {label} has been reached. Please try again tomorrow.")
        return AIError("rate_limit", "The AI service is busy or a usage limit was reached. Please wait a minute and try again.")
    if isinstance(error, openai.AuthenticationError):
        return AIError("auth", f"The API key was rejected by {label}. Check {settings.key_name} in your settings.")
    if isinstance(error, openai.PermissionDeniedError):
        return AIError("permission", f"This API key cannot use the configured model on {label}.")
    if isinstance(error, openai.NotFoundError):
        return AIError("model", "The configured AI model was not found. Check NYAYSAATHI_MODEL in your settings.")
    if isinstance(error, openai.APITimeoutError):
        return AIError("timeout", "The AI service took too long to reply. Please try again.")
    if isinstance(error, openai.APIConnectionError):
        return AIError("connection", "Could not reach the AI service. Check the internet connection.")
    if isinstance(error, openai.BadRequestError):
        return AIError("bad_request", f"The AI service rejected the request: {getattr(error, 'message', error)}")
    if isinstance(error, openai.APIStatusError):
        return AIError("server", f"The AI service returned error {error.status_code}. Please try again shortly.")
    return AIError("unknown", f"Unexpected AI error: {type(error).__name__}")


def parse_json(response: LLMResponse) -> dict:
    """Parse a structured response. Bad JSON becomes an AIError rather than a crash."""
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as error:
        raise AIError("bad_json", "The AI returned an unreadable answer. Please try again.") from error


@dataclass
class CallRecord:
    """One AI call, exactly as sent and received. Raw test outputs are built from these."""

    timestamp: str
    schema_name: str
    fast: bool
    system: str
    messages: list[dict]
    response_text: str
    model: str
    provider: str
    input_tokens: int | None
    output_tokens: int | None
    is_mock: bool


@dataclass
class RecordingProvider:
    """Wraps a provider and records every call, for the evaluation's raw outputs."""

    inner: LLMProvider
    calls: list[CallRecord] = field(default_factory=list)
    pause_seconds: float = 0.0  # Wait before each call, to stay under free-tier limits.

    def _complete_with_patience(self, *args) -> LLMResponse:
        if self.pause_seconds:
            time.sleep(self.pause_seconds)
        try:
            return self.inner.complete(*args)
        except AIError as error:
            if not self.pause_seconds or error.kind != "rate_limit":
                raise
        time.sleep(RATE_LIMIT_WAIT_SECONDS)  # Per-minute limits clear within a minute.
        return self.inner.complete(*args)

    def complete(self, system, messages, schema=None, schema_name="response", fast=False) -> LLMResponse:
        response = self._complete_with_patience(system, messages, schema, schema_name, fast)
        self.calls.append(
            CallRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                schema_name=schema_name,
                fast=fast,
                system=system,
                messages=[dict(message) for message in messages],
                response_text=response.text,
                model=response.model,
                provider=response.provider,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                is_mock=response.is_mock,
            )
        )
        return response

    def transcribe(self, audio, filename, language=None) -> str:
        return self.inner.transcribe(audio, filename, language)

    def calls_as_dicts(self) -> list[dict]:
        return [asdict(call) for call in self.calls]


def get_provider(settings: Settings) -> LLMProvider:
    if settings.provider == "mock":
        from core.mock_provider import MockProvider

        return MockProvider()
    if settings.provider == "openai":
        return OpenAIProvider(settings)
    return ChatCompatibleProvider(settings)
