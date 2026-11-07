"""Tests the provider code with a fake client. No network calls, so these prove our side only."""

from types import SimpleNamespace

import openai
import pytest

import config
from core import ai_engine
from core.ai_engine import AIError, ChatCompatibleProvider, OpenAIProvider, RecordingProvider, get_provider, _to_ai_error


def settings(provider="gemini", effort=None, api_key="test-key"):
    preset = config.PROVIDERS[provider]
    return config.Settings(
        api_key=api_key,
        provider=provider,
        model=preset.model or "company-model",
        fast_model=preset.fast_model or "company-model",
        transcribe_model=preset.transcribe_model or "company-model",
        effort=effort or preset.effort,
        max_tokens=100,
        base_url=preset.base_url or "https://example.test/v1",
        provider_label=preset.label,
        key_name=preset.key_name,
    )


def reply(content="hello", finish_reason="stop", refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        model="served-model",
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
    )


def provider_with(response, chosen=None):
    provider = ChatCompatibleProvider(chosen or settings())
    sent = {}

    def create(**request):
        sent.update(request)
        return response

    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider, sent


def rate_limit_error(message):
    response = SimpleNamespace(request=None, status_code=429, headers={})
    return openai.RateLimitError(message, response=response, body=None)


def test_get_provider_picks_the_class_from_settings():
    assert isinstance(get_provider(settings("gemini")), ChatCompatibleProvider)
    assert isinstance(get_provider(settings("compatible")), ChatCompatibleProvider)
    assert isinstance(get_provider(settings("openai")), OpenAIProvider)


def test_missing_key_names_the_setting_to_add():
    with pytest.raises(AIError, match="GEMINI_API_KEY"):
        get_provider(settings(api_key=None))


def test_complete_sends_system_message_schema_and_effort():
    provider, sent = provider_with(reply('{"a": 1}'))
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    response = provider.complete("rules", [{"role": "user", "content": "hi"}], schema=schema, schema_name="thing", fast=True)

    assert sent["model"] == config.PROVIDERS["gemini"].fast_model
    assert sent["messages"][0] == {"role": "system", "content": "rules"}
    assert sent["messages"][1] == {"role": "user", "content": "hi"}
    assert sent["reasoning_effort"] == "low"
    assert sent["response_format"]["json_schema"] == {"name": "thing", "strict": True, "schema": schema}
    assert (response.text, response.model, response.provider) == ('{"a": 1}', "served-model", "gemini")
    assert (response.input_tokens, response.output_tokens) == (3, 4)


def test_default_effort_sends_no_effort_setting():
    provider, sent = provider_with(reply(), settings("compatible"))
    provider.complete("rules", [{"role": "user", "content": "hi"}])
    assert "reasoning_effort" not in sent
    assert "response_format" not in sent


@pytest.mark.parametrize(
    "response, kind",
    [
        (reply("part of an", finish_reason="length"), "incomplete"),
        (reply(None, finish_reason="content_filter"), "refusal"),
        (reply(None, refusal="no"), "refusal"),
        (reply(None), "failed"),
        (reply(""), "failed"),
    ],
)
def test_unusable_answers_become_clear_errors(response, kind):
    provider, _ = provider_with(response)
    with pytest.raises(AIError) as caught:
        provider.complete("rules", [{"role": "user", "content": "hi"}])
    assert caught.value.kind == kind


def test_transcribe_sends_the_audio_in_a_chat_message():
    provider, sent = provider_with(reply("  mera refund nahi aaya  "))
    assert provider.transcribe(b"abc", "speech.wav", "hi") == "mera refund nahi aaya"
    text_part, audio_part = sent["messages"][0]["content"]
    assert "hi" in text_part["text"]
    assert audio_part["input_audio"] == {"data": "YWJj", "format": "wav"}
    assert sent["model"] == config.PROVIDERS["gemini"].transcribe_model


def test_gemini_quota_errors_are_not_reported_as_missing_credit():
    per_minute = _to_ai_error(rate_limit_error("exceeded quota: GenerateRequestsPerMinutePerProject"), settings())
    per_day = _to_ai_error(rate_limit_error("exceeded quota: GenerateRequestsPerDayPerProject"), settings())
    assert per_minute.kind == "rate_limit"
    assert per_day.kind == "daily_limit"
    assert "credit" not in per_day.user_message


def test_openai_quota_error_still_reports_missing_credit():
    error = _to_ai_error(rate_limit_error("insufficient_quota"), settings("openai"))
    assert error.kind == "no_credit"


class Flaky:
    def __init__(self, errors):
        self.errors = list(errors)
        self.attempts = 0

    def complete(self, *args):
        self.attempts += 1
        if self.errors:
            raise self.errors.pop(0)
        return ai_engine.LLMResponse(text="ok", model="m", provider="gemini")


def test_recording_provider_waits_and_retries_once_after_a_rate_limit(monkeypatch):
    waits = []
    monkeypatch.setattr(ai_engine.time, "sleep", waits.append)
    inner = Flaky([AIError("rate_limit", "busy")])
    recording = RecordingProvider(inner, pause_seconds=7)
    assert recording.complete("s", [{"role": "user", "content": "x"}]).text == "ok"
    assert inner.attempts == 2
    assert waits == [7, ai_engine.RATE_LIMIT_WAIT_SECONDS]
    assert len(recording.calls) == 1


@pytest.mark.parametrize("kind", ["daily_limit", "auth"])
def test_recording_provider_does_not_retry_other_errors(monkeypatch, kind):
    monkeypatch.setattr(ai_engine.time, "sleep", lambda _: None)
    inner = Flaky([AIError(kind, "stop")])
    with pytest.raises(AIError):
        RecordingProvider(inner, pause_seconds=7).complete("s", [{"role": "user", "content": "x"}])
    assert inner.attempts == 1
