"""Generates draft documents. Code, not the AI, adds the draft warning and signature lines."""

import io
from dataclasses import dataclass, field
from datetime import date

from docx import Document as WordDocument
from docx.shared import Pt, RGBColor

from core import prompts
from core.ai_engine import LLMProvider, parse_json
from core.case_builder import invented_numbers
from core.citation_validator import remove_unsupported_sentences, strip_citation_tags
from core.legal_retrieval import KnowledgeBase, format_for_prompt
from core.rights import find_sources

DRAFT_WARNING = "DRAFT – FOR USER REVIEW. NOT A LAWYER-VERIFIED LEGAL DOCUMENT."
NOT_SENT_NOTICE = "NyaySaathi has not sent or filed this document. You decide whether and how to use it."

DOCUMENT_TYPES = {
    "refund_request": "Refund request to the company",
    "support_complaint": "Formal complaint to customer support",
    "grievance_representation": "Consumer grievance representation",
    "draft_consumer_complaint": "Draft consumer complaint for review",
    "response_to_company": "Response to a company's reply",
}

SENDER_BLOCK = "[YOUR FULL NAME]\n[YOUR ADDRESS]\n[YOUR PHONE NUMBER]\n[YOUR EMAIL ADDRESS]"
CLOSING_BLOCK = "Date: [DATE]\nPlace: [PLACE]\n\nSignature: [YOUR SIGNATURE]\nName: [YOUR FULL NAME]"


@dataclass
class GeneratedDocument:
    document_type: str
    text: str
    warnings: list[str] = field(default_factory=list)


def _render(fields: dict) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- [TO BE ADDED]"

    return "\n\n".join(
        (
            DRAFT_WARNING,
            f"From:\n{SENDER_BLOCK}",
            f"To:\n{fields['recipient']}",
            f"Subject: {fields['subject']}",
            f"Relevant facts:\n{bullets(fields['facts'])}",
            f"Timeline of events:\n{bullets(fields['timeline'])}",
            f"Grievance:\n{fields['grievance']}",
            f"Remedy requested:\n{fields['requested_remedy']}",
            f"Supporting evidence:\n{bullets(fields['supporting_evidence'])}",
            CLOSING_BLOCK,
            DRAFT_WARNING,
        )
    )


def generate_document(
    provider: LLMProvider,
    knowledge_base: KnowledgeBase,
    document_type: str,
    case_text: str,
    user_text: str,
    extra_instructions: str = "",
    today: date | None = None,
) -> GeneratedDocument:
    """Draft a document. Unsupported legal sentences are removed; invented numbers are flagged."""
    sources = find_sources(knowledge_base, case_text, today)
    retrieved_ids = {result.provision.id for result in sources}
    system = (
        f"{prompts.DOCUMENT_SYSTEM}\n\nWrite the document in English, unless the user's note asks otherwise.\n\n"
        f"DOCUMENT TYPE: {DOCUMENT_TYPES[document_type]}. {prompts.DOCUMENT_BRIEFS[document_type]}\n\n"
        f"VERIFIED SOURCES:\n{format_for_prompt(sources)}"
    )
    content = f"Case:\n{case_text}"
    if extra_instructions.strip():
        content += f"\n\nNote from the user:\n{extra_instructions.strip()}"
    response = provider.complete(
        system,
        [{"role": "user", "content": content}],
        schema=prompts.DOCUMENT_SCHEMA,
        schema_name="document",
    )
    fields = parse_json(response)

    warnings: list[str] = []

    def clean(text: str) -> str:
        kept, removed = remove_unsupported_sentences(text, retrieved_ids, knowledge_base, today)
        warnings.extend(f"Removed an unsupported legal statement: \"{sentence}\"" for sentence in removed)
        return strip_citation_tags(kept)

    for key in ("recipient", "subject", "grievance", "requested_remedy"):
        fields[key] = clean(fields[key])
    for key in ("facts", "timeline", "supporting_evidence"):
        fields[key] = [cleaned for cleaned in (clean(item) for item in fields[key]) if cleaned]

    # Compare numbers against both the user's words and the sources, because a cited provision may
    # legitimately contain numbers such as a section number or a year.
    allowed = "\n".join(
        (
            user_text,
            case_text,
            extra_instructions,
            *(f"{r.provision.label} {r.provision.quote} {r.provision.plain_language}" for r in sources),
        )
    )
    text = _render(fields)
    body_without_warning = text.replace(DRAFT_WARNING, "")
    for number in sorted(invented_numbers(body_without_warning, allowed)):
        warnings.append(f"Please check the number {number}. It did not come from what you told us.")
    return GeneratedDocument(document_type, text, warnings)


def to_docx(text: str) -> bytes:
    """Turn the edited document text into a Word file, keeping the draft warning prominent."""
    document = WordDocument()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)

    if not text.lstrip().startswith(DRAFT_WARNING):
        text = f"{DRAFT_WARNING}\n\n{text}"
    for block in text.split("\n\n"):
        paragraph = document.add_paragraph()
        if block.strip() == DRAFT_WARNING:
            run = paragraph.add_run(block.strip())
            run.bold = True
            run.font.color.rgb = RGBColor(0xB9, 0x1C, 0x1C)
            continue
        for index, line in enumerate(block.split("\n")):
            if index:
                paragraph.add_run().add_break()
            run = paragraph.add_run(line)
            if index == 0 and line.endswith(":") or line.startswith("Subject:"):
                run.bold = True

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def to_txt(text: str) -> bytes:
    if not text.lstrip().startswith(DRAFT_WARNING):
        text = f"{DRAFT_WARNING}\n\n{text}"
    return text.encode("utf-8")
