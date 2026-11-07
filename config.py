"""Central settings for NyaySaathi.

Every setting is read in this order:
  1. Environment variables, including those loaded from a local .env file.
  2. Streamlit secrets, which is where Streamlit Community Cloud keeps them.
  3. The default written below.

The API key is never printed or logged by this module.
"""

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
RAW_OUTPUTS_DIR = PROJECT_ROOT / "raw_outputs"
TEST_CASES_FILE = PROJECT_ROOT / "data" / "test_cases.json"

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass(frozen=True)
class ProviderPreset:
    """What one AI provider needs. Any preset value except the key can be overridden in .env."""

    label: str
    key_name: str
    model: str | None
    fast_model: str | None
    transcribe_model: str | None
    effort: str
    base_url: str | None = None


# Swapping the AI is a settings change: NYAYSAATHI_PROVIDER picks one of these.
_GEMINI = ProviderPreset(
    label="Google Gemini",
    key_name="GEMINI_API_KEY",
    # gemini-3.8-flash failed 3 of 3 free-tier calls with error 503 on 2026-11-07; this one answered 3 of 3.
    model="gemini-3.6-flash",
    fast_model="gemini-3.5-flash-lite",
    transcribe_model="gemini-3.6-flash",
    effort="low",
    base_url=GEMINI_BASE_URL,
)
PROVIDERS = {
    "gemini": _GEMINI,
    "openai": ProviderPreset("OpenAI", "OPENAI_API_KEY", "gpt-5.4", "gpt-5.4-mini", "gpt-4o-mini-transcribe", "low"),
    # Any other service with an OpenAI-style API, such as one a company provides.
    "compatible": ProviderPreset("the configured AI provider", "NYAYSAATHI_API_KEY", None, None, None, "default"),
    "mock": replace(_GEMINI, label="no external AI (MOCK mode)"),
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = _GEMINI.model
DEFAULT_EFFORT = _GEMINI.effort
DEFAULT_MAX_TOKENS = 8000
VALID_PROVIDERS = tuple(PROVIDERS)
# "default" sends no effort setting at all, for models that do not accept one.
VALID_EFFORTS = ("default", "none", "minimal", "low", "medium", "high", "xhigh", "max")

# A real shell variable wins over .env, because override is False.
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _read_setting(name: str) -> str | None:
    """Return a setting's value, or None if it is missing or blank."""
    value = os.environ.get(name, "").strip()
    if value:
        return value

    # Streamlit does not copy secrets into os.environ until they are first read,
    # so a deployed app has to ask for them directly.
    try:
        import streamlit as st

        value = str(st.secrets.get(name, "")).strip()
    except Exception:  # Streamlit raises when no secrets file exists.
        return None
    return value or None


@dataclass(frozen=True)
class Settings:
    # repr=False keeps the key out of logs and error messages.
    api_key: str | None = field(repr=False)
    provider: str
    model: str
    fast_model: str
    transcribe_model: str
    effort: str
    max_tokens: int
    base_url: str | None = None
    provider_label: str = ""
    key_name: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"


def load_settings() -> Settings:
    """Read and validate settings. A bad value raises ValueError with a clear message."""
    provider = (_read_setting("NYAYSAATHI_PROVIDER") or DEFAULT_PROVIDER).lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"NYAYSAATHI_PROVIDER must be one of {', '.join(VALID_PROVIDERS)}; got {provider!r}."
        )

    preset = PROVIDERS[provider]
    model = _read_setting("NYAYSAATHI_MODEL") or preset.model
    base_url = _read_setting("NYAYSAATHI_BASE_URL") or preset.base_url
    if provider == "compatible" and not (model and base_url):
        raise ValueError("NYAYSAATHI_PROVIDER=compatible also needs NYAYSAATHI_BASE_URL and NYAYSAATHI_MODEL.")

    effort = _read_setting("NYAYSAATHI_EFFORT") or preset.effort
    if effort not in VALID_EFFORTS:
        raise ValueError(
            f"NYAYSAATHI_EFFORT must be one of {', '.join(VALID_EFFORTS)}; got {effort!r}."
        )

    raw_max_tokens = _read_setting("NYAYSAATHI_MAX_TOKENS") or str(DEFAULT_MAX_TOKENS)
    try:
        max_tokens = int(raw_max_tokens)
    except ValueError:
        max_tokens = 0
    if max_tokens <= 0:
        raise ValueError(
            f"NYAYSAATHI_MAX_TOKENS must be a positive whole number; got {raw_max_tokens!r}."
        )

    return Settings(
        api_key=_read_setting(preset.key_name),
        provider=provider,
        model=model,
        fast_model=_read_setting("NYAYSAATHI_FAST_MODEL") or preset.fast_model or model,
        transcribe_model=_read_setting("NYAYSAATHI_TRANSCRIBE_MODEL") or preset.transcribe_model or model,
        effort=effort,
        max_tokens=max_tokens,
        base_url=base_url,
        provider_label=preset.label,
        key_name=preset.key_name,
    )
