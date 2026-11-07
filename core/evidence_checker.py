"""Builds a case-specific evidence checklist, and never claims evidence the user did not mention."""

from core import prompts
from core.ai_engine import LLMProvider, parse_json
from core.case_builder import normalise

USER_MENTIONED = "user_mentioned"
NOT_MENTIONED = "not_mentioned"


def check_items(items: list[dict], user_text: str) -> list[dict]:
    """Mark an item as held by the user only if their quoted words are really in the conversation."""
    checked = []
    normalised_user_text = normalise(user_text)
    for item in items:
        item = dict(item)
        quote = item.get("user_quote", "")
        if item["status"] == USER_MENTIONED and (not quote.strip() or normalise(quote) not in normalised_user_text):
            item["status"] = NOT_MENTIONED
            item["user_quote"] = ""
        checked.append(item)
    return checked


def build_checklist(provider: LLMProvider, case_text: str, user_text: str, language: str = "english") -> list[dict]:
    system = f"{prompts.EVIDENCE_SYSTEM}\n\n{prompts.language_instruction(language)}"
    content = f"Case:\n{case_text}\n\nEverything the user said, word for word:\n{user_text}"
    response = provider.complete(
        system,
        [{"role": "user", "content": content}],
        schema=prompts.EVIDENCE_SCHEMA,
        schema_name="evidence_checklist",
        fast=True,
    )
    return check_items(parse_json(response)["items"], user_text)
