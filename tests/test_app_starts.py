"""Clicks through the real app in Streamlit's test harness, using the labelled MOCK provider."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import document_generator
from ui.common import _STRINGS
from ui.pages import PAGES

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
STORY = (
    "I ordered a mobile phone online for Rs. 25,000. The company delivered a defective phone. "
    "I returned it but have not received my refund even after 30 days and I want the money back now."
)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "mock")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


def go(app, page):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception


def click(app, label):
    matches = [button for button in app.button if label in button.label]
    assert matches, f"No button containing {label!r}: {[b.label for b in app.button]}"
    matches[0].click().run()
    assert not app.exception


def page_text(app):
    return " ".join(element.value for element in app.markdown)


def test_every_page_opens_without_errors(app):
    for page in PAGES:
        go(app, page)


def test_navigation_labels_exist_in_both_languages():
    for key in PAGES:
        assert all(_STRINGS[key])


def test_home_has_the_required_content_and_no_fake_claims(app):
    text = page_text(app)
    for expected in ("NyaySaathi", "Understand Your Rights", "How it works", "Problems we can help with", "not a lawyer"):
        assert expected in text
    assert any("Start Your Case" in button.label for button in app.button)
    for fake in ("testimonial", "% success", "users trust"):
        assert fake not in text.lower()


def test_mock_mode_is_visibly_labelled(app):
    assert "MOCK MODE" in page_text(app)


def test_start_button_opens_the_chat(app):
    click(app, "Start Your Case")
    assert app.title[0].value == "AI Legal Chat"


def test_hindi_labels_appear_when_hindi_is_selected(app):
    app.sidebar.selectbox[0].set_value("hindi").run()
    assert not app.exception
    assert "अपना केस शुरू करें" in [button.label for button in app.button]


def _send(app, text):
    go(app, "nav_chat")
    app.text_area[0].set_value(text)
    click(app, "Send")


def test_chat_shows_privacy_notice_and_answer(app):
    go(app, "nav_chat")
    assert "sent to no external AI (MOCK mode)" in page_text(app)
    _send(app, STORY)
    assert "MOCK RESPONSE" in page_text(app)
    assert app.session_state["conversation"].messages[0]["content"] == STORY


def test_gemini_privacy_notice_warns_about_free_tier_use_of_content(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "gemini")
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    go(app, "nav_chat")
    text = page_text(app)
    assert "sent to Google Gemini" in text
    assert "improve its products" in text


def test_full_journey_chat_case_rights_evidence_document_practice(app):
    _send(app, STORY)
    go(app, "nav_case")
    click(app, "Build my case")
    assert app.session_state["case"]["title"] == "MOCK case file"
    # Editing a fact marks it as coming from the user.
    field = next(item for item in app.text_input if item.label == "Amount involved")
    field.set_value("Rs. 25,000").run()
    assert not app.exception
    assert app.session_state["case"]["amount_involved"]["provenance"] == "user_stated"

    go(app, "nav_rights")
    click(app, "Find my rights")
    assert "Read the official source" in page_text(app)
    assert any("lawyer" in step["title"].lower() for step in app.session_state["action_plan"]["steps"])

    go(app, "nav_evidence")
    click(app, "Create my checklist")
    assert app.checkbox and not app.checkbox[0].value

    go(app, "nav_docs")
    click(app, "Generate draft")
    editor = next(area for area in app.text_area if area.label == "Your document")
    assert editor.value.startswith(document_generator.DRAFT_WARNING)
    assert document_generator.DRAFT_WARNING in page_text(app)

    go(app, "nav_practice")
    assert "Practice only" in page_text(app)
    click(app, "Start practice")
    app.chat_input[0].set_value("I want my refund").run()
    assert not app.exception
    click(app, "End practice")
    assert "Questions to prepare for" in page_text(app)


def test_typed_story_and_edited_document_survive_changing_pages(app):
    go(app, "nav_case")
    app.text_area[0].set_value(STORY).run()
    click(app, "Build my case")
    go(app, "nav_about")
    assert app.session_state["manual_story"] == STORY

    go(app, "nav_docs")
    click(app, "Generate draft")
    editor = next(area for area in app.text_area if area.label == "Your document")
    edited = editor.value + "\nMy own added line."
    editor.set_value(edited).run()
    go(app, "nav_about")
    go(app, "nav_docs")
    editor = next(area for area in app.text_area if area.label == "Your document")
    assert editor.value == edited


def test_pages_that_need_a_case_say_so(app):
    for page in ("nav_rights", "nav_docs", "nav_evidence"):
        go(app, page)
        assert "build your case" in page_text(app)


def test_delete_clears_everything(app):
    _send(app, STORY)
    assert app.session_state["conversation"] is not None
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert app.session_state["conversation"] is None
    assert any("deleted" in message.value for message in app.success)


def test_missing_api_key_gives_a_clear_message_not_a_crash(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr("config._read_setting", _settings_without_key(monkeypatch))
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    _send(app, STORY)
    assert any("API key" in message.value for message in app.error)


def _settings_without_key(monkeypatch):
    import os

    def read(name):
        return None if name == "OPENAI_API_KEY" else (os.environ.get(name) or None)

    return read


def test_api_key_is_never_displayed(monkeypatch):
    monkeypatch.setenv("NYAYSAATHI_PROVIDER", "mock")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value-123")
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    for page in PAGES:
        go(app, page)
        assert "secret-value-123" not in page_text(app)
