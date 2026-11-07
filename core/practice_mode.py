"""Practice Your Argument: the AI plays a company representative, then gives feedback.

This is rehearsal only. Replies are checked so that the character cannot state law
or mention court cases, since no sources are retrieved here.
"""

from core import prompts
from core.ai_engine import LLMProvider, parse_json
from core.citation_validator import LEGAL_REFERENCE, CASE_LAW, CASE_NAME, SENSITIVE_CLAIM

PRACTICE_LABEL = "Practice only. This is a simulation, not a real company representative or legal proceeding."
ROLES = {
    "customer_support": "customer support representative",
    "seller": "seller's representative",
    "legal_team": "company's legal team member",
}
_SAFE_PRACTICE_REPLY = (
    "I understand your concern. Could you please share your order details and any proof you have, "
    "so that I can look into this?"
)


def contains_legal_claim(text: str) -> bool:
    return any(pattern.search(text) for pattern in (LEGAL_REFERENCE, CASE_LAW, CASE_NAME, SENSITIVE_CLAIM))


class PracticeSession:
    def __init__(self, provider: LLMProvider, case_summary: str, role: str = "customer_support", language: str = "english"):
        self.provider = provider
        self.system = prompts.PRACTICE_SYSTEM.format(
            role=ROLES[role],
            case_summary=case_summary or "The user has not built a case yet. Ask them to explain their complaint.",
            language=prompts.language_instruction(language),
        )
        self.language = language
        self.messages: list[dict] = []

    def say(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        reply = self.provider.complete(self.system, self.messages).text
        if contains_legal_claim(reply):
            reply = _SAFE_PRACTICE_REPLY
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def feedback(self) -> dict:
        lines = [
            f"{'User' if message['role'] == 'user' else 'Representative'}: {message['content']}"
            for message in self.messages
        ]
        system = f"{prompts.FEEDBACK_SYSTEM}\n\n{prompts.language_instruction(self.language)}"
        response = self.provider.complete(
            system,
            [{"role": "user", "content": "Practice conversation:\n" + "\n".join(lines)}],
            schema=prompts.FEEDBACK_SCHEMA,
            schema_name="practice_feedback",
        )
        return parse_json(response)
