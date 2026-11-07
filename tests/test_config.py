"""Tests for config.py. These make no API calls and need no real key."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

SETTING_NAMES = (
    "GEMINI_API_KEY", "OPENAI_API_KEY", "NYAYSAATHI_API_KEY", "NYAYSAATHI_BASE_URL",
    "NYAYSAATHI_MODEL", "NYAYSAATHI_FAST_MODEL", "NYAYSAATHI_EFFORT",
    "NYAYSAATHI_MAX_TOKENS", "NYAYSAATHI_PROVIDER", "NYAYSAATHI_TRANSCRIBE_MODEL",
)


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    """Run each test from a blank state, whatever is in the developer's .env."""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    # Stop the Streamlit secrets fallback from reading real files on this machine.
    monkeypatch.setitem(sys.modules, "streamlit", None)


def test_defaults_apply_when_nothing_is_configured():
    settings = config.load_settings()
    assert settings.model == config.DEFAULT_MODEL
    assert settings.effort == config.DEFAULT_EFFORT
    assert settings.max_tokens == config.DEFAULT_MAX_TOKENS
    assert settings.has_api_key is False


def test_blank_api_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert config.load_settings().has_api_key is False


def test_gemini_free_tier_is_the_default():
    settings = config.load_settings()
    assert settings.provider == "gemini"
    assert settings.base_url == config.GEMINI_BASE_URL
    assert settings.key_name == "GEMINI_API_KEY"


def test_each_provider_reads_only_its_own_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    assert config.load_settings().has_api_key is False
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "openai")
    settings = config.load_settings()
    assert settings.api_key == "openai-key"
    assert settings.model == "gpt-5.4"
    assert settings.base_url is None


def test_a_company_api_can_be_connected_with_settings_alone(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "compatible")
    monkeypatch.setenv("NYAYSAATHI_API_KEY", "company-key")
    monkeypatch.setenv("NYAYSAATHI_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("NYAYSAATHI_MODEL", "stronger-model")
    settings = config.load_settings()
    assert (settings.api_key, settings.base_url) == ("company-key", "https://models.example.test/v1")
    assert settings.model == settings.fast_model == settings.transcribe_model == "stronger-model"
    assert settings.effort == "default"


def test_compatible_provider_without_an_address_is_rejected(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "compatible")
    with pytest.raises(ValueError, match="NYAYSAATHI_BASE_URL"):
        config.load_settings()


def test_model_can_be_changed_from_the_environment(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_MODEL", "some-other-model")
    assert config.load_settings().model == "some-other-model"


def test_api_key_never_appears_in_text_form(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value-123")
    settings = config.load_settings()
    assert settings.has_api_key is True
    assert "secret-value-123" not in repr(settings)
    assert "secret-value-123" not in str(settings)


def test_invalid_effort_is_rejected(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_EFFORT", "extreme")
    with pytest.raises(ValueError, match="NYAYSAATHI_EFFORT"):
        config.load_settings()


@pytest.mark.parametrize("bad_value", ["abc", "0", "-5"])
def test_invalid_max_tokens_is_rejected(monkeypatch, bad_value):
    monkeypatch.setenv("NYAYSAATHI_MAX_TOKENS", bad_value)
    with pytest.raises(ValueError, match="NYAYSAATHI_MAX_TOKENS"):
        config.load_settings()


def test_mock_mode_is_explicit(monkeypatch):
    assert config.load_settings().is_mock is False
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "mock")
    assert config.load_settings().is_mock is True


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "something-else")
    with pytest.raises(ValueError, match="NYAYSAATHI_PROVIDER"):
        config.load_settings()


def test_public_files_contain_no_real_api_key():
    """Guards the files that go to GitHub. A real key belongs only in .env."""
    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|AQ\.[A-Za-z0-9_-]{20,}")
    public_files = [root / ".env.example", root / ".streamlit" / "secrets.toml.example", root / "README.md"]
    leaking = [path.name for path in public_files if path.exists() and pattern.search(path.read_text())]
    assert not leaking, f"Remove the API key from: {leaking}"


def test_env_example_leaves_every_key_blank():
    """Catches a key of any format, including ones the pattern above has never seen."""
    template = (Path(__file__).resolve().parent.parent / ".env.example").read_text()
    filled = re.findall(r"^([A-Z_]*API_KEY)=\S", template, re.MULTILINE)
    assert not filled, f"Keys belong in .env, not .env.example: {filled}"
