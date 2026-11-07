"""A scripted stand-in for the AI, used to test code and view the interface with no API credit.

Its answers are fixed and say MOCK. They show that the program's plumbing works.
They say nothing about the quality of a real AI's answers, and must never be
submitted as real results.
"""

import json
import re

from core.ai_engine import LLMResponse

MOCK_MODEL = "MOCK-not-a-real-model"
_SOURCE_TAG = re.compile(r"\[SRC:([A-Za-z0-9_-]+)\]")


def _retrieved_ids(system: str) -> list[str]:
    """Citation IDs from the sources section only, not from examples in the instructions."""
    _, _, sources = system.partition("VERIFIED SOURCES:")
    return list(dict.fromkeys(_SOURCE_TAG.findall(sources)))


def _fact(text: str, provenance: str = "unverified", quote: str = "") -> dict:
    return {"text": text, "provenance": provenance, "user_quote": quote}


class MockProvider:
    def complete(self, system, messages, schema=None, schema_name="response", fast=False) -> LLMResponse:
        last = messages[-1]["content"] if messages else ""
        builder = getattr(self, f"_build_{schema_name}", None)
        text = json.dumps(builder(system, last), ensure_ascii=False) if builder else self._chat(system, last)
        return LLMResponse(
            text=text,
            model=MOCK_MODEL,
            provider="mock",
            input_tokens=None,
            output_tokens=None,
            is_mock=True,
        )

    def transcribe(self, audio, filename, language=None) -> str:
        return "MOCK transcription. Real speech-to-text was not used."

    @staticmethod
    def _chat(system, last) -> str:
        sources = _retrieved_ids(system)
        if "fact-gathering" in system:
            return (
                "MOCK RESPONSE: I understand there is a problem with your purchase.\n"
                "1. When did you buy it?\n2. Which company or platform was it from?\n"
                "3. Do you have the invoice?\n4. Have you contacted customer support?"
            )
        if "role-playing" in system:
            return "MOCK RESPONSE: Could you please share your order number and proof of purchase?"
        if sources:
            return f"MOCK RESPONSE: A verified source may be relevant to your situation [SRC:{sources[0]}]."
        return "MOCK RESPONSE: I could not verify the exact legal provision. Please consult a qualified lawyer."

    @staticmethod
    def _build_triage(system, last) -> dict:
        lowered = last.lower()
        out = bool(re.search(r"divorce|custody|landlord|bail|तलाक", lowered))
        ready = len(last.split()) > 25
        return {
            "scope": "out_of_scope" if out else "in_scope",
            "stage": "ready" if ready else "gathering",
            "category": "not_a_consumer_issue" if out else "other_consumer_issue",
            "needs_lawyer_reasons": [],
            "english_search_terms": "refund defective product online seller",
            "missing_facts": ["MOCK: purchase date"],
        }

    @staticmethod
    def _build_case_file(system, last) -> dict:
        return {
            "title": "MOCK case file",
            "nature_of_dispute": "MOCK: a consumer dispute, described by the user.",
            "category": "other_consumer_issue",
            "consumer": _fact("MOCK: the user"),
            "opposite_parties": [_fact("MOCK: the company named by the user")],
            "timeline": [{"date_text": "Date not given", "event": _fact("MOCK: the user described a problem")}],
            "amount_involved": _fact("MOCK: not given"),
            "company_promised": [_fact("MOCK: not given")],
            "what_happened": [_fact("MOCK: the user described a problem")],
            "evidence_available": [],
            "evidence_required": ["Purchase invoice", "Payment receipt"],
            "missing_information": ["Date of purchase"],
            "desired_resolution": _fact("MOCK: not given"),
        }

    @staticmethod
    def _build_rights_cards(system, last) -> dict:
        ids = _retrieved_ids(system)[:3]
        return {"cards": [{"source_id": i, "how_it_may_relate": "MOCK: this may relate to the case."} for i in ids]}

    @staticmethod
    def _build_evidence_checklist(system, last) -> dict:
        return {
            "items": [
                {
                    "item": "Purchase invoice",
                    "why_it_matters": "MOCK: it can show what you bought and when.",
                    "status": "not_mentioned",
                    "user_quote": "",
                },
                {
                    "item": "Payment receipt",
                    "why_it_matters": "MOCK: it can show the amount you paid.",
                    "status": "not_mentioned",
                    "user_quote": "",
                },
            ]
        }

    @staticmethod
    def _build_action_plan(system, last) -> dict:
        return {
            "steps": [
                {"title": "Collect your proof", "detail": "MOCK: gather your invoice and payment receipt."},
                {"title": "Write to the company", "detail": "MOCK: send a written complaint and keep a copy."},
            ]
        }

    @staticmethod
    def _build_document(system, last) -> dict:
        return {
            "recipient": "[COMPANY NAME]\n[COMPANY ADDRESS]",
            "subject": "MOCK: complaint regarding [PRODUCT OR SERVICE]",
            "facts": ["MOCK: I bought [PRODUCT OR SERVICE] on [DATE OF PURCHASE]."],
            "timeline": ["[DATE]: MOCK: the problem occurred."],
            "grievance": "MOCK: the product or service did not meet what was promised.",
            "requested_remedy": "MOCK: please resolve this by [RESPONSE DATE].",
            "supporting_evidence": ["[LIST OF DOCUMENTS]"],
        }

    @staticmethod
    def _build_practice_feedback(system, last) -> dict:
        return {
            "clarity": "MOCK: feedback is not real.",
            "evidence_presented": "MOCK: feedback is not real.",
            "missing_facts": ["MOCK: order number"],
            "strength_of_explanation": "MOCK: feedback is not real.",
            "questions_to_prepare_for": ["MOCK: when did you buy it?"],
        }
