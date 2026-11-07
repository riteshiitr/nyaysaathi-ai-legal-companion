"""Runs one chat turn: safety check, classify, find the law, answer, check, retry or block."""

import re
from dataclasses import dataclass, field
from datetime import date

from core import prompts, safety_guardrails
from core.ai_engine import AIError, LLMProvider, parse_json
from core.citation_validator import (
    UNVERIFIED_STATEMENT,
    Confidence,
    ValidationReport,
    strip_citation_tags,
    validate,
)
from core.legal_retrieval import KnowledgeBase, SearchResult, format_for_prompt

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[^\W\d_]")
_HINGLISH_WORDS = frozenset(
    """hai hain nahi nhi mera meri mere maine mujhe mujhko aur kya kyu kyun kaise kab kahan tha thi
    raha rahi gaya gayi liya kiya kar karo karna paisa paise wapas vapas kharab bhai ji abhi tak
    bola bataya diya mila mili hua hui lekin ke ka ki se ko bhi""".split()
)
MIN_HINGLISH_WORDS = 2
MAX_CORRECTION_ATTEMPTS = 1

OUT_OF_SCOPE_REPLY = {
    "english": (
        "This looks like it falls outside what I can help with. NyaySaathi only covers consumer disputes and "
        "refund complaints, so I should not guess about this kind of matter. Please speak to a qualified lawyer. "
        "If I have misunderstood and this is about something you bought or a service you paid for, please tell me more."
    ),
    "hindi": (
        "यह मामला उस दायरे से बाहर लगता है जिसमें मैं मदद कर सकता हूँ। न्यायसाथी केवल उपभोक्ता विवादों और रिफंड की शिकायतों के लिए है, "
        "इसलिए इस तरह के मामले में मुझे अनुमान नहीं लगाना चाहिए। कृपया किसी योग्य वकील से बात करें। "
        "अगर मैंने गलत समझा है और यह किसी खरीदी गई चीज़ या सेवा के बारे में है, तो कृपया और बताएँ।"
    ),
    "hinglish": (
        "Yeh mamla mere scope se bahar lagta hai. NyaySaathi sirf consumer disputes aur refund complaints ke liye hai, "
        "isliye is tarah ke mamle mein mujhe andaza nahi lagana chahiye. Kripya kisi qualified lawyer se baat karein. "
        "Agar maine galat samjha hai aur yeh kisi kharidi hui cheez ya service ke baare mein hai, toh please aur batayein."
    ),
}

BLOCKED_REPLY = {
    "english": UNVERIFIED_STATEMENT,
    "hindi": "मैं सटीक कानूनी प्रावधान की पुष्टि नहीं कर सका। कृपया किसी योग्य वकील से सलाह लें या आधिकारिक सरकारी स्रोत देखें।",
    "hinglish": "Main exact legal provision verify nahi kar paya. Kripya kisi qualified lawyer se salah lein ya official government source check karein.",
}


def detect_language(text: str) -> str:
    """Classify text as english, hindi or hinglish, using its script and common words."""
    letters = _LETTER.findall(text)
    if letters and len(_DEVANAGARI.findall(text)) / len(letters) > 0.3:
        return "hindi"
    words = re.findall(r"[a-z]+", text.lower())
    return "hinglish" if sum(word in _HINGLISH_WORDS for word in words) >= MIN_HINGLISH_WORDS else "english"


def language_matches(text: str, language: str) -> bool:
    """Check the reply's script. Hinglish and English are hard to separate, so only script is tested."""
    visible = strip_citation_tags(text)
    letters = _LETTER.findall(visible)
    if not letters:
        return True
    devanagari_share = len(_DEVANAGARI.findall(visible)) / len(letters)
    return devanagari_share > 0.5 if language == "hindi" else devanagari_share < 0.1


@dataclass
class AssistantTurn:
    text: str
    display_text: str
    language: str
    stage: str
    scope: str
    category: str
    sources: list[SearchResult] = field(default_factory=list)  # Cited in the answer the user sees.
    retrieved: list[SearchResult] = field(default_factory=list)  # Everything given to the AI.
    report: ValidationReport | None = None
    confidence: Confidence | None = None
    lawyer_reasons: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    correction_attempts: int = 0
    blocked: bool = False


class Conversation:
    """One user's chat. It lives only in memory, for the length of the session."""

    def __init__(
        self,
        provider: LLMProvider,
        knowledge_base: KnowledgeBase,
        preferred_language: str = "auto",
        today: date | None = None,
    ):
        self.provider = provider
        self.knowledge_base = knowledge_base
        self.preferred_language = preferred_language
        self.today = today
        self.messages: list[dict] = []
        self.turns: list[AssistantTurn] = []
        self.language: str | None = None
        self.category = "other_consumer_issue"

    @property
    def user_text(self) -> str:
        return "\n".join(message["content"] for message in self.messages if message["role"] == "user")

    def transcript(self) -> str:
        lines = []
        for message in self.messages:
            speaker = "User" if message["role"] == "user" else "Assistant"
            lines.append(f"{speaker}: {strip_citation_tags(message['content'])}")
        return "\n".join(lines)

    def _resolve_language(self, text: str) -> str:
        if self.preferred_language != "auto":
            return self.preferred_language
        # A short reply such as "yes" or "25000" should not switch the language.
        if self.language and len(text.split()) < 4 and not _DEVANAGARI.search(text):
            return self.language
        return detect_language(text)

    def _triage(self) -> dict | None:
        """Classify with AI. Returns None on bad output, so the safety rules can still run."""
        response = self.provider.complete(
            prompts.TRIAGE_SYSTEM,
            self.messages,
            schema=prompts.TRIAGE_SCHEMA,
            schema_name="triage",
            fast=True,
        )
        try:
            return parse_json(response)
        except AIError as error:
            if error.kind == "bad_json":
                return None
            raise

    def respond(self, user_text: str) -> AssistantTurn:
        """Process a user message. If the AI service fails, the message is taken back so it can be retried."""
        language = self._resolve_language(user_text)
        self.language = language
        self.messages.append({"role": "user", "content": user_text})
        try:
            turn = self._respond(language)
        except AIError:
            self.messages.pop()
            raise
        self.messages.append({"role": "assistant", "content": turn.text})
        self.turns.append(turn)
        return turn

    def _respond(self, language: str) -> AssistantTurn:
        rule_check = safety_guardrails.assess(self.user_text)
        triage = self._triage() or {
            "scope": "unclear",
            "stage": "gathering",
            "category": "other_consumer_issue",
            "needs_lawyer_reasons": [],
            "english_search_terms": "",
            "missing_facts": [],
        }
        self.category = triage["category"]
        lawyer_reasons = list(dict.fromkeys([*rule_check.reasons, *triage["needs_lawyer_reasons"]]))

        # A rule match alone does not end the chat, because "salary" or "landlord" can appear in a
        # genuine consumer story. The AI's classification and the absence of any consumer signal decide.
        rules_say_out = safety_guardrails.OUT_OF_SCOPE in rule_check.flags
        if triage["scope"] == "out_of_scope" or (rules_say_out and triage["scope"] == "unclear"):
            return self._finish(
                OUT_OF_SCOPE_REPLY[language], language, "out_of_scope", "out_of_scope", triage, lawyer_reasons
            )

        if triage["stage"] == "gathering":
            system = f"{prompts.GATHERING_SYSTEM}\n\n{prompts.language_instruction(language)}"
            reply = self.provider.complete(system, self.messages).text
            return self._finish(reply, language, "gathering", triage["scope"], triage, lawyer_reasons)

        return self._advise(language, triage, lawyer_reasons)

    def _advise(self, language: str, triage: dict, lawyer_reasons: list[str]) -> AssistantTurn:
        query = f"{triage['english_search_terms']}\n{self.user_text}"
        sources = self.knowledge_base.search(query, top_k=10, today=self.today)
        retrieved_ids = {result.provision.id for result in sources}

        system = (
            f"{prompts.ADVICE_SYSTEM}\n\n{prompts.language_instruction(language)}\n\n"
            f"VERIFIED SOURCES:\n{format_for_prompt(sources)}"
        )
        messages = list(self.messages)
        reply = self.provider.complete(system, messages).text

        report = validate(reply, retrieved_ids, self.knowledge_base, self.today)
        attempts = 0
        while attempts < MAX_CORRECTION_ATTEMPTS and not self._passes(reply, report, language):
            attempts += 1
            problems = report.problems()
            if not language_matches(reply, language):
                problems.append(f"Wrong language. {prompts.language_instruction(language)}")
            note = prompts.CORRECTION_NOTE.format(problems="\n".join(f"- {p}" for p in problems))
            retry_messages = [
                *messages,
                {"role": "assistant", "content": reply},
                {"role": "user", "content": note},
            ]
            reply = self.provider.complete(system, retry_messages).text
            report = validate(reply, retrieved_ids, self.knowledge_base, self.today)

        blocked = not report.is_clean
        if blocked:
            # Unsupported legal text is never shown, even after a retry.
            reply = BLOCKED_REPLY[language]
            report_for_display = validate(reply, retrieved_ids, self.knowledge_base, self.today)
        else:
            report_for_display = report

        turn = self._finish(reply, language, "ready", triage["scope"], triage, lawyer_reasons)
        turn.sources = [
            result for result in sources if result.provision.id in report_for_display.valid_citations
        ]
        turn.retrieved = sources
        turn.report = report  # Keeps what was actually detected, including in a blocked answer.
        turn.confidence = report_for_display.confidence
        turn.correction_attempts = attempts
        turn.blocked = blocked
        return turn

    @staticmethod
    def _passes(reply: str, report: ValidationReport, language: str) -> bool:
        return report.is_clean and language_matches(reply, language)

    def _finish(
        self,
        reply: str,
        language: str,
        stage: str,
        scope: str,
        triage: dict,
        lawyer_reasons: list[str],
    ) -> AssistantTurn:
        return AssistantTurn(
            text=reply,
            display_text=strip_citation_tags(reply),
            language=language,
            stage=stage,
            scope=scope,
            category=triage["category"],
            lawyer_reasons=lawyer_reasons,
            missing_facts=triage["missing_facts"],
        )
