"""Builds legal information cards and the action plan from a case and verified sources.

Everything on a card about the law comes straight from the knowledge base. The AI
only chooses relevant provisions and writes how each may relate to the case.
"""

from dataclasses import dataclass
from datetime import date

from core import prompts
from core.ai_engine import LLMProvider, parse_json
from core.citation_validator import (
    UNVERIFIED_STATEMENT,
    Confidence,
    remove_unsupported_sentences,
    strip_citation_tags,
    validate,
)
from core.legal_retrieval import KnowledgeBase, Provision, SearchResult, format_for_prompt

# These apply to almost every dispute, so they are always offered to the AI.
ALWAYS_OFFER = ("CPA2019-S69", "NCH-CONTACT", "CPA2019-S35-1", "EJAGRITI-LIMITATION-DOCS")

LAWYER_STEP = {
    "title": "Consider speaking to a qualified lawyer",
    "detail": (
        "A lawyer can advise on your specific facts, especially if legal representation is needed, "
        "a deadline may be close, or important legal questions remain unanswered."
    ),
}
NO_GUARANTEE = "These steps are general information. They do not guarantee any particular outcome."


@dataclass
class RightsCard:
    provision: Provision
    how_it_may_relate: str
    verification_status: str
    confidence: Confidence


def find_sources(
    knowledge_base: KnowledgeBase, case_text: str, today: date | None = None
) -> list[SearchResult]:
    results = knowledge_base.search(case_text, top_k=12, today=today)
    found = {result.provision.id for result in results}
    for provision_id in ALWAYS_OFFER:
        if provision_id not in found:
            provision = knowledge_base.provisions[provision_id]
            results.append(SearchResult(provision, 0.0, not provision.is_in_force(today or date.today())))
    return results


def build_rights_cards(
    provider: LLMProvider,
    knowledge_base: KnowledgeBase,
    case_text: str,
    language: str = "english",
    today: date | None = None,
) -> list[RightsCard]:
    """Return cards for provisions the AI judged relevant. Unknown IDs are dropped."""
    sources = find_sources(knowledge_base, case_text, today)
    by_id = {result.provision.id: result for result in sources}
    system = (
        f"{prompts.RIGHTS_SYSTEM}\n\n{prompts.language_instruction(language)}\n\n"
        f"VERIFIED SOURCES:\n{format_for_prompt(sources)}"
    )
    response = provider.complete(
        system,
        [{"role": "user", "content": f"Case:\n{case_text}"}],
        schema=prompts.RIGHTS_SCHEMA,
        schema_name="rights_cards",
    )

    cards = []
    for raw in parse_json(response)["cards"]:
        source_id = raw["source_id"].replace("[", "").replace("]", "").removeprefix("SRC:")
        result = by_id.get(source_id)
        if result is None:
            continue
        explanation, _removed = remove_unsupported_sentences(
            raw["how_it_may_relate"], set(by_id), knowledge_base, today
        )
        if result.not_yet_in_force:
            status = f"Verified, but not in force until {result.provision.in_force_from.isoformat()}"
            confidence = Confidence.PARTIAL
        else:
            status = f"Verified against the official source on {result.provision.document.last_verified}"
            confidence = Confidence.SUPPORTED
        cards.append(RightsCard(result.provision, explanation, status, confidence))
    return cards


def build_action_plan(
    provider: LLMProvider,
    knowledge_base: KnowledgeBase,
    case_text: str,
    language: str = "english",
    today: date | None = None,
) -> dict:
    """Return validated steps. Sentences that fail the citation check are removed and reported."""
    sources = find_sources(knowledge_base, case_text, today)
    retrieved_ids = {result.provision.id for result in sources}
    system = (
        f"{prompts.PLAN_SYSTEM}\n\n{prompts.language_instruction(language)}\n\n"
        f"VERIFIED SOURCES:\n{format_for_prompt(sources)}"
    )
    response = provider.complete(
        system,
        [{"role": "user", "content": f"Case:\n{case_text}"}],
        schema=prompts.PLAN_SCHEMA,
        schema_name="action_plan",
    )

    steps, removed, valid_citations = [], [], set()
    for step in parse_json(response)["steps"]:
        report = validate(step["detail"], retrieved_ids, knowledge_base, today)
        valid_citations.update(report.valid_citations)
        detail, dropped = remove_unsupported_sentences(step["detail"], retrieved_ids, knowledge_base, today)
        removed.extend(dropped)
        if detail:
            steps.append({"title": step["title"], "detail": strip_citation_tags(detail)})
    steps.append(dict(LAWYER_STEP))

    return {
        "steps": steps,
        "removed_sentences": removed,
        "sources": [knowledge_base.provisions[provision_id] for provision_id in sorted(valid_citations)],
        "no_guarantee_notice": NO_GUARANTEE,
        "unverified_notice": UNVERIFIED_STATEMENT if removed else "",
    }
