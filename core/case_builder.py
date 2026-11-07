"""Turns a conversation into an organised case file, then checks it for invented facts.

The AI labels where each fact came from. This module does not simply trust those
labels: a fact marked as stated by the user must quote the user's real words, and
any number in it must appear in what the user said. Otherwise the fact is
downgraded to "unverified" and flagged, so it is easy to spot and correct.
"""

import re
import unicodedata

from core import prompts
from core.ai_engine import LLMProvider, parse_json

USER_STATED = "user_stated"
AI_INFERENCE = "ai_inference"
UNVERIFIED = "unverified"

PROVENANCE_LABELS = {
    USER_STATED: "Provided by you",
    AI_INFERENCE: "AI inference",
    UNVERIFIED: "Not verified",
}

_FACT_LISTS = ("opposite_parties", "company_promised", "what_happened", "evidence_available")
_SINGLE_FACTS = ("consumer", "amount_involved", "desired_resolution")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalise(text: str) -> str:
    """Compare text while ignoring case, spacing and punctuation."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\W_]+", "", text)


def numbers_in(text: str) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER.findall(unicodedata.normalize("NFKC", text))}


def invented_numbers(text: str, source_text: str) -> set[str]:
    """Numbers in the text that do not appear in the source."""
    return numbers_in(text) - numbers_in(source_text)


def _check_fact(fact: dict, user_text: str, warnings: list[str]) -> None:
    """Downgrade a fact that its supposed source does not support. Changes the fact in place."""
    text = fact["text"]
    if not text.strip():
        return
    fact.setdefault("flagged", False)
    if fact["provenance"] == USER_STATED:
        quote = fact.get("user_quote", "")
        if not quote.strip() or normalise(quote) not in normalise(user_text):
            fact["provenance"] = UNVERIFIED
            fact["flagged"] = True
            warnings.append(f'Could not find this in what you said, so it is marked unverified: "{text}"')
    extra = invented_numbers(text, user_text)
    if extra:
        fact["provenance"] = UNVERIFIED
        fact["flagged"] = True
        warnings.append(f"This contains a number you did not mention ({', '.join(sorted(extra))}): \"{text}\"")


def check_case(case: dict, user_text: str) -> dict:
    """Validate a case against the user's actual words. Adds a 'warnings' list."""
    warnings: list[str] = []
    for key in _SINGLE_FACTS:
        _check_fact(case[key], user_text, warnings)
    for key in _FACT_LISTS:
        for fact in case[key]:
            _check_fact(fact, user_text, warnings)
    for entry in case["timeline"]:
        _check_fact(entry["event"], user_text, warnings)
        extra = invented_numbers(entry["date_text"], user_text)
        if extra:
            entry["event"]["provenance"] = UNVERIFIED
            entry["event"]["flagged"] = True
            warnings.append(f"This date contains a number you did not mention: \"{entry['date_text']}\"")

    # Evidence must never be claimed unless the user really said they have it.
    confirmed, unconfirmed = [], []
    for fact in case["evidence_available"]:
        (confirmed if fact["provenance"] == USER_STATED else unconfirmed).append(fact)
    case["evidence_available"] = confirmed
    for fact in unconfirmed:
        if fact["text"] not in case["evidence_required"]:
            case["evidence_required"].append(fact["text"])

    case["warnings"] = warnings
    return case


def build_case(provider: LLMProvider, transcript: str, user_text: str) -> dict:
    system = prompts.CASE_SYSTEM
    messages = [{"role": "user", "content": f"Conversation:\n{transcript}"}]
    response = provider.complete(system, messages, schema=prompts.CASE_SCHEMA, schema_name="case_file", fast=True)
    return check_case(parse_json(response), user_text)


def _fact_line(fact: dict) -> str:
    return f"{fact['text']} ({PROVENANCE_LABELS.get(fact['provenance'], fact['provenance'])})"


def case_to_text(case: dict) -> str:
    """Plain-text summary of the case, shown to the AI by later steps. User edits are included."""
    lines = [f"Title: {case['title']}", f"Nature of dispute: {case['nature_of_dispute']}"]
    lines.append(f"Consumer: {_fact_line(case['consumer'])}")
    lines.append("Opposite parties: " + "; ".join(_fact_line(f) for f in case["opposite_parties"]))
    lines.append(f"Amount involved: {_fact_line(case['amount_involved'])}")
    lines.append("Timeline:")
    lines.extend(f"- {entry['date_text']}: {_fact_line(entry['event'])}" for entry in case["timeline"])
    lines.append("What the company promised:")
    lines.extend(f"- {_fact_line(fact)}" for fact in case["company_promised"])
    lines.append("What actually happened:")
    lines.extend(f"- {_fact_line(fact)}" for fact in case["what_happened"])
    lines.append("Evidence the user has:")
    lines.extend(f"- {_fact_line(fact)}" for fact in case["evidence_available"])
    lines.append("Evidence still required: " + "; ".join(case["evidence_required"]))
    lines.append("Missing information: " + "; ".join(case["missing_information"]))
    lines.append(f"Desired resolution: {_fact_line(case['desired_resolution'])}")
    return "\n".join(lines)
