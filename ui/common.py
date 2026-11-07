
"""Shared helpers for NyaySaathi: session state, AI access, translations and display."""

import html

import streamlit as st

from config import load_settings
from core.ai_engine import AIError, get_provider
from core.citation_validator import Confidence
from core.conversation import Conversation
from core.legal_retrieval import KnowledgeBase, load_knowledge_base


DISCLAIMER = (
    "NyaySaathi is an AI tool that provides legal information. It is not a lawyer, does not represent you, "
    "and does not create a lawyer-client relationship. Its answers can be wrong or incomplete. "
    "Please check important points with a qualified lawyer or the official government source."
)


def privacy_notice() -> str:
    """Explain who receives the user's information and how it is handled."""
    settings = load_settings()

    free_tier = (
        "On the free tier, Google may use what you send to improve its products, "
        "so please use made-up names and details. "
        if settings.provider == "gemini"
        else ""
    )

    return (
        f"What you type or record is sent to {settings.provider_label} to generate answers. "
        f"{free_tier}"
        "NyaySaathi keeps it only for this browser session and does not save it permanently. "
        "Please do not share details you do not need to, such as bank passwords, OTPs or Aadhaar numbers."
    )


# ---------- Interface text ----------

_STRINGS = {
    "nav_home": ("Home", "होम"),
    "nav_chat": ("AI Legal Chat", "एआई कानूनी चैट"),
    "nav_case": ("Build My Case", "मेरा केस बनाएँ"),
    "nav_rights": ("Know My Rights", "मेरे अधिकार जानें"),
    "nav_docs": ("Generate Documents", "दस्तावेज़ बनाएँ"),
    "nav_evidence": ("Evidence Checklist", "सबूतों की सूची"),
    "nav_practice": ("Practice My Argument", "अपनी बात का अभ्यास"),
    "nav_about": ("About / Legal Disclaimer", "परिचय / कानूनी सूचना"),

    "tagline": (
        "Understand Your Rights. Know Your Options. Take Action.",
        "अपने अधिकार समझें। अपने विकल्प जानें। कदम उठाएँ।",
    ),

    "hero_text": (
        "Tell us about a problem with something you bought or a service you paid for. NyaySaathi helps you "
        "organise the facts, understand your options using verified Indian consumer-law sources, and prepare "
        "documents to take action.",
        "आपने जो चीज़ खरीदी या जिस सेवा के पैसे दिए, उसमें आई समस्या के बारे में बताएँ। न्यायसाथी तथ्यों को व्यवस्थित करने, "
        "सत्यापित भारतीय उपभोक्ता कानून स्रोतों से अपने विकल्प समझने और कदम उठाने के लिए दस्तावेज़ तैयार करने में मदद करता है।",
    ),

    "start": ("Start Your Case", "अपना केस शुरू करें"),
    "problems": ("Problems we can help with", "हम इन समस्याओं में मदद कर सकते हैं"),
    "how": ("How it works", "यह कैसे काम करता है"),
    "language": ("Answer language", "जवाब की भाषा"),
    "delete": ("Delete my conversation", "मेरी बातचीत मिटाएँ"),
    "type_here": ("Describe your problem in your own words", "अपनी समस्या अपने शब्दों में बताएँ"),
    "send": ("Send", "भेजें"),
}


LANGUAGE_OPTIONS = {
    "auto": "Automatic",
    "english": "English",
    "hindi": "हिन्दी (Hindi)",
    "hinglish": "Hinglish",
}


CONFIDENCE_CLASS = {
    Confidence.SUPPORTED: "supported",
    Confidence.PARTIAL: "partial",
    Confidence.INSUFFICIENT: "insufficient",
}


def t(key: str) -> str:
    """Translate an interface label."""
    english, hindi = _STRINGS[key]
    return hindi if st.session_state.get("language_pref") == "hindi" else english


# ---------- Knowledge base ----------

@st.cache_resource
def knowledge_base() -> KnowledgeBase:
    return load_knowledge_base()


# ---------- AI provider ----------

def provider():
    """Return the AI provider for this session, or None after showing why it is unavailable."""
    try:
        return get_provider(load_settings())
    except (AIError, ValueError) as error:
        st.error(error.user_message if isinstance(error, AIError) else str(error))
        return None


def is_mock_mode() -> bool:
    return load_settings().is_mock


# ---------- Session state ----------

def init_state() -> None:
    defaults = {
        "page": "nav_home",
        "language_pref": "auto",
        "conversation": None,
        "chat_draft": "",
        "pending_message": None,
        "last_audio_hash": None,
        "manual_story": "",
        "case": None,
        "case_version": 0,
        "rights_cards": None,
        "action_plan": None,
        "evidence": None,
        "document": None,
        "document_text": "",
        "document_version": 0,
        "practice": None,
        "practice_feedback": None,
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def delete_everything() -> None:
    """Clear all of this session's data."""
    language = st.session_state.get("language_pref", "auto")

    st.session_state.clear()
    init_state()

    st.session_state.language_pref = language
    st.session_state.just_deleted = True


# ---------- Conversation ----------

def get_conversation() -> Conversation | None:
    if st.session_state.conversation is None:
        ai = provider()

        if ai is None:
            return None

        st.session_state.conversation = Conversation(ai, knowledge_base())

    conversation = st.session_state.conversation
    conversation.preferred_language = st.session_state.language_pref

    return conversation


def working_language() -> str:
    """The language for generated content: the user's choice, or that of their conversation."""
    preference = st.session_state.language_pref

    if preference != "auto":
        return preference

    conversation = st.session_state.conversation

    return (
        conversation.language
        if conversation and conversation.language
        else "english"
    )


def user_words() -> str:
    """Everything the user has told us, which is what facts are checked against."""
    conversation = st.session_state.conversation
    chat_text = conversation.user_text if conversation else ""

    return "\n".join(
        part
        for part in (chat_text, st.session_state.manual_story)
        if part
    )


def transcript() -> str:
    conversation = st.session_state.conversation

    chat = (
        conversation.transcript()
        if conversation and conversation.messages
        else ""
    )

    story = st.session_state.manual_story

    return "\n".join(
        part
        for part in (chat, f"User: {story}" if story else "")
        if part
    )


# ---------- AI task execution ----------

def run_ai(label: str, function, *args, **kwargs):
    """Run an AI task with a progress message."""
    try:
        with st.spinner(label):
            return function(*args, **kwargs)

    except AIError as error:
        st.error(error.user_message)
        return None


# ---------- Navigation ----------

def go_to(page: str) -> None:
    st.session_state.page = page


# ---------- Shared display elements ----------

def note(text: str, kind: str = "") -> None:
    """Display a consistent notice across application pages."""
    safe_text = html.escape(str(text))
    safe_kind = html.escape(kind, quote=True)

    st.markdown(
        f'<div class="ns-note {safe_kind}">{safe_text}</div>',
        unsafe_allow_html=True,
    )


def confidence_badge(confidence: Confidence) -> str:
    """Return the styled confidence indicator."""
    css_class = CONFIDENCE_CLASS[confidence]

    return (
        f'<span class="ns-badge {css_class}">'
        f'{html.escape(confidence.value)}'
        f'</span>'
    )


def need_case() -> bool:
    """Show a pointer to Build My Case when no case exists."""
    if st.session_state.case:
        return True

    note(
        "First, tell us about your problem and build your case. "
        "The other pages use that case.",
        "info",
    )

    st.button(
        "Go to Build My Case",
        on_click=go_to,
        args=("nav_case",),
        type="primary",
    )

    return False
