"""Tests the safety logic around the AI, using scripted AI answers.

These prove what our CODE does with good and bad AI output. They cannot show how
good a real AI's answers are; the evaluation suite measures that.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import case_builder, document_generator, evidence_checker, practice_mode, rights, safety_guardrails  # noqa: E402
from core.ai_engine import AIError, LLMResponse, RecordingProvider  # noqa: E402
from core.citation_validator import Confidence  # noqa: E402
from core.conversation import Conversation, detect_language, language_matches  # noqa: E402
from core.legal_retrieval import load_knowledge_base  # noqa: E402
from core.mock_provider import MockProvider  # noqa: E402

TODAY = date(2026, 11, 7)
REFUND_STORY = (
    "I ordered a mobile phone online for Rs. 25,000. The company delivered a defective phone. "
    "I returned it but have not received my refund even after 30 days."
)


class ScriptedProvider:
    """Returns prepared answers in order, and records what it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def complete(self, system, messages, schema=None, schema_name="response", fast=False):
        self.requests.append({"system": system, "messages": list(messages), "schema_name": schema_name})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        text = json.dumps(answer, ensure_ascii=False) if isinstance(answer, dict) else answer
        return LLMResponse(text=text, model="scripted", provider="test")


def triage(scope="in_scope", stage="ready", terms="defective phone refund refused online", reasons=()):
    return {
        "scope": scope,
        "stage": stage,
        "category": "company_refusing_refund",
        "needs_lawyer_reasons": list(reasons),
        "english_search_terms": terms,
        "missing_facts": [],
    }


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def chat(kb, *answers, language="auto"):
    return Conversation(ScriptedProvider(*answers), kb, preferred_language=language, today=TODAY)


GOOD_ANSWER = "Refusing a refund for defective goods is listed as an unfair trade practice [SRC:CPA2019-S2-47-viii]."


def test_good_answer_passes_first_time(kb):
    turn = chat(kb, triage(), GOOD_ANSWER).respond(REFUND_STORY)
    assert turn.correction_attempts == 0
    assert turn.confidence is Confidence.SUPPORTED
    assert not turn.blocked
    assert "[SRC:" not in turn.display_text
    assert [r.provision.id for r in turn.sources] == ["CPA2019-S2-47-viii"]


def test_fabricated_section_triggers_a_retry_then_uses_the_corrected_answer(kb):
    conversation = chat(kb, triage(), "Section 420 guarantees your refund.", GOOD_ANSWER)
    turn = conversation.respond(REFUND_STORY)
    assert turn.correction_attempts == 1
    assert not turn.blocked
    assert "420" not in turn.text
    assert "Section 420" in conversation.provider.requests[-1]["messages"][-1]["content"]


def test_answer_that_stays_fabricated_is_blocked_and_never_shown(kb):
    turn = chat(kb, triage(), "Section 420 guarantees it.", "In Sharma v. Flipkart you won.").respond(REFUND_STORY)
    assert turn.blocked is True
    assert "420" not in turn.display_text and "Sharma" not in turn.display_text
    assert "could not verify" in turn.display_text
    assert turn.confidence is Confidence.INSUFFICIENT
    assert turn.report.case_law_mentions


def test_invented_citation_id_is_blocked(kb):
    turn = chat(kb, triage(), "Refund now [SRC:FAKE-1].", "Refund now [SRC:FAKE-1].").respond(REFUND_STORY)
    assert turn.blocked is True


def test_wrong_language_triggers_a_retry(kb):
    hindi_answer = "रिफंड न देना अनुचित व्यापार व्यवहार के रूप में सूचीबद्ध है [SRC:CPA2019-S2-47-viii]।"
    conversation = chat(kb, triage(), GOOD_ANSWER, hindi_answer)
    turn = conversation.respond("मैंने फोन खरीदा था, वह खराब निकला और कंपनी पैसे वापस नहीं कर रही है।")
    assert turn.language == "hindi"
    assert turn.correction_attempts == 1
    assert language_matches(turn.text, "hindi")


def test_gathering_stage_gets_no_legal_sources(kb):
    conversation = chat(kb, triage(stage="gathering"), "1. When did you buy it?")
    turn = conversation.respond("My phone is bad")
    assert turn.stage == "gathering"
    assert turn.confidence is None
    assert "VERIFIED SOURCES" not in conversation.provider.requests[1]["system"]


def test_out_of_scope_gets_a_fixed_reply_with_no_second_ai_call(kb):
    conversation = chat(kb, triage(scope="out_of_scope"))
    turn = conversation.respond("I want a divorce from my husband")
    assert turn.stage == "out_of_scope"
    assert "lawyer" in turn.display_text.lower()
    assert len(conversation.provider.requests) == 1


def test_safety_rules_still_escalate_if_ai_triage_output_is_unreadable(kb):
    conversation = chat(kb, "this is not json")
    turn = conversation.respond("I want a divorce and custody of my child")
    assert turn.stage == "out_of_scope"


def test_rule_flags_are_added_even_when_the_ai_finds_nothing(kb):
    story = f"{REFUND_STORY} They also threatened me and took Rs. 2 crore."
    turn = chat(kb, triage(), GOOD_ANSWER).respond(story)
    assert any("criminal" in reason for reason in turn.lawyer_reasons)
    assert any("large" in reason for reason in turn.lawyer_reasons)


def test_ai_failure_takes_back_the_message_so_it_can_be_retried(kb):
    error = AIError("no_credit", "No credit")
    conversation = chat(kb, error)
    with pytest.raises(AIError):
        conversation.respond(REFUND_STORY)
    assert conversation.messages == []


def test_conversation_context_is_sent_on_the_next_turn(kb):
    conversation = chat(kb, triage(stage="gathering"), "When?", triage(stage="gathering"), "Which company?")
    conversation.respond("My phone is bad")
    conversation.respond("Last week")
    assert [m["content"] for m in conversation.provider.requests[-1]["messages"]][:3] == ["My phone is bad", "When?", "Last week"]


@pytest.mark.parametrize(
    "text, expected",
    [
        (REFUND_STORY, "english"),
        ("मेरा फोन खराब है और रिफंड नहीं मिला", "hindi"),
        ("maine phone liya tha, kharab nikla aur paisa wapas nahi mila", "hinglish"),
    ],
)
def test_language_detection(text, expected):
    assert detect_language(text) == expected


def test_selected_language_overrides_detection(kb):
    conversation = chat(kb, triage(stage="gathering"), "कब?", language="hindi")
    assert conversation.respond("My phone is bad").language == "hindi"


def test_short_reply_keeps_the_conversation_language(kb):
    conversation = chat(kb, triage(stage="gathering"), "kab?", triage(stage="gathering"), "kahan?")
    assert conversation.respond("maine phone liya tha, kharab nikla").language == "hinglish"
    assert conversation.respond("ok").language == "hinglish"


@pytest.mark.parametrize(
    "text, flag",
    [
        ("I want a divorce", safety_guardrails.OUT_OF_SCOPE),
        ("मुझे तलाक चाहिए", safety_guardrails.OUT_OF_SCOPE),
        ("They threatened me on the phone", safety_guardrails.CRIMINAL),
        ("yeh dhokha hai, police ke paas jaunga", safety_guardrails.CRIMINAL),
        ("My hearing is tomorrow", safety_guardrails.URGENT),
        ("The heater exploded and I was injured", safety_guardrails.HARM),
        ("I paid Rs. 75 lakh for a flat", safety_guardrails.HIGH_VALUE),
        ("I paid ₹60,00,000", safety_guardrails.HIGH_VALUE),
        ("I received a legal notice", safety_guardrails.LITIGATION),
    ],
)
def test_safety_rules_detect(text, flag):
    assert flag in safety_guardrails.assess(text).flags


def test_ordinary_refund_story_raises_no_safety_flags():
    assert safety_guardrails.assess(REFUND_STORY).flags == []


def _case(**overrides):
    case = MockProvider._build_case_file("", "")
    case.update(overrides)
    return case


def test_fact_with_a_real_quote_stays_user_stated():
    fact = {"text": "Paid Rs. 25,000", "provenance": "user_stated", "user_quote": "for Rs. 25,000"}
    case = case_builder.check_case(_case(amount_involved=fact), REFUND_STORY)
    assert case["amount_involved"]["provenance"] == "user_stated"


def test_fact_with_a_made_up_quote_is_downgraded():
    fact = {"text": "Bought on Amazon", "provenance": "user_stated", "user_quote": "I bought it on Amazon"}
    case = case_builder.check_case(_case(opposite_parties=[fact]), REFUND_STORY)
    assert case["opposite_parties"][0]["provenance"] == "unverified"
    assert case["warnings"]


def test_invented_amount_is_downgraded_even_when_labelled_as_inference():
    fact = {"text": "Paid Rs. 99,999", "provenance": "ai_inference", "user_quote": ""}
    case = case_builder.check_case(_case(amount_involved=fact), REFUND_STORY)
    assert case["amount_involved"]["provenance"] == "unverified"
    assert "99999" in case["warnings"][0]


def test_invented_date_is_flagged():
    entry = {"date_text": "12 March 2026", "event": {"text": "Bought phone", "provenance": "ai_inference", "user_quote": ""}}
    case = case_builder.check_case(_case(timeline=[entry]), REFUND_STORY)
    assert case["timeline"][0]["event"]["provenance"] == "unverified"


def test_evidence_the_user_did_not_mention_moves_to_required():
    fact = {"text": "Invoice", "provenance": "ai_inference", "user_quote": ""}
    case = case_builder.check_case(_case(evidence_available=[fact]), REFUND_STORY)
    assert case["evidence_available"] == []
    assert "Invoice" in case["evidence_required"]


def test_checklist_cannot_claim_evidence_without_the_users_words():
    items = [
        {"item": "Invoice", "why_it_matters": "x", "status": "user_mentioned", "user_quote": "I have the invoice"},
        {"item": "Refund", "why_it_matters": "x", "status": "user_mentioned", "user_quote": "have not received my refund"},
    ]
    checked = evidence_checker.check_items(items, REFUND_STORY)
    assert checked[0]["status"] == "not_mentioned"
    assert checked[1]["status"] == "user_mentioned"


def test_rights_cards_take_the_law_from_the_knowledge_base_and_drop_unknown_ids(kb):
    provider = ScriptedProvider(
        {
            "cards": [
                {"source_id": "CPA2019-S69", "how_it_may_relate": "This may matter for your timing."},
                {"source_id": "FAKE-999", "how_it_may_relate": "Invented."},
            ]
        }
    )
    cards = rights.build_rights_cards(provider, kb, REFUND_STORY, today=TODAY)
    assert [card.provision.id for card in cards] == ["CPA2019-S69"]
    assert cards[0].provision.document.url.startswith("https://www.indiacode.nic.in")
    assert "Verified" in cards[0].verification_status
    assert cards[0].confidence is Confidence.SUPPORTED


def test_action_plan_removes_unsupported_claims_and_always_adds_a_lawyer_step(kb):
    provider = ScriptedProvider(
        {
            "steps": [
                {
                    "title": "File",
                    "detail": "Keep your invoice. Section 420 guarantees a win. You may file within two years [SRC:CPA2019-S69].",
                }
            ]
        }
    )
    plan = rights.build_action_plan(provider, kb, REFUND_STORY, today=TODAY)
    assert "420" not in plan["steps"][0]["detail"]
    assert "[SRC:" not in plan["steps"][0]["detail"]
    assert "two years" in plan["steps"][0]["detail"]
    assert plan["removed_sentences"] == ["Section 420 guarantees a win."]
    assert "lawyer" in plan["steps"][-1]["title"].lower()
    assert [source.id for source in plan["sources"]] == ["CPA2019-S69"]


def _document_answer(**overrides):
    answer = MockProvider._build_document("", "")
    answer.update(overrides)
    return answer


def test_document_always_has_the_draft_warning_and_required_sections(kb):
    provider = ScriptedProvider(_document_answer())
    document = document_generator.generate_document(
        provider, kb, "refund_request", REFUND_STORY, REFUND_STORY, today=TODAY
    )
    text = document.text
    assert text.startswith(document_generator.DRAFT_WARNING)
    for required in ("From:", "To:", "Subject:", "Relevant facts:", "Timeline of events:", "Grievance:",
                     "Remedy requested:", "Supporting evidence:", "Date:", "Signature:"):
        assert required in text


def test_document_flags_invented_numbers_and_removes_fake_law(kb):
    answer = _document_answer(
        facts=["I paid Rs. 25,000.", "My order number is 884422."],
        grievance="Section 420 entitles me to a refund. The phone was defective.",
    )
    document = document_generator.generate_document(
        ScriptedProvider(answer), kb, "support_complaint", REFUND_STORY, REFUND_STORY, today=TODAY
    )
    assert "420" not in document.text
    assert "The phone was defective." in document.text
    assert any("884422" in warning for warning in document.warnings)
    assert not any("25000" in warning for warning in document.warnings)


@pytest.mark.parametrize("document_type", list(document_generator.DOCUMENT_TYPES))
def test_every_document_type_can_be_generated(kb, document_type):
    document = document_generator.generate_document(
        MockProvider(), kb, document_type, REFUND_STORY, REFUND_STORY, today=TODAY
    )
    assert document_generator.DRAFT_WARNING in document.text


def test_downloads_keep_the_warning_even_if_the_user_deleted_it():
    assert document_generator.to_txt("Hello").startswith(document_generator.DRAFT_WARNING.encode())
    from docx import Document as WordDocument
    import io

    word = WordDocument(io.BytesIO(document_generator.to_docx("From:\nMe\n\nHello")))
    assert word.paragraphs[0].text == document_generator.DRAFT_WARNING
    assert any("Hello" in paragraph.text for paragraph in word.paragraphs)


def test_practice_character_cannot_state_law():
    session = practice_mode.PracticeSession(ScriptedProvider("Under Section 420 you get nothing."), "case")
    assert "420" not in session.say("I want my refund")


def test_practice_feedback_has_every_section():
    session = practice_mode.PracticeSession(MockProvider(), "case")
    session.say("I want my refund")
    assert set(session.feedback()) == {
        "clarity", "evidence_presented", "missing_facts", "strength_of_explanation", "questions_to_prepare_for",
    }


def test_full_flow_with_mock_is_labelled_and_recorded(kb):
    provider = RecordingProvider(MockProvider())
    conversation = Conversation(provider, kb, today=TODAY)
    turn = conversation.respond(REFUND_STORY)
    assert "MOCK" in turn.display_text
    assert provider.calls and all(call.is_mock for call in provider.calls)
