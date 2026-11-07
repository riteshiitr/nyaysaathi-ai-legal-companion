"""Scores one test run against the 10 criteria, using automated checks only.

Each criterion returns pass, fail or not_applicable, with its evidence. These
checks catch specific measurable failures. They cannot judge whether legal
reasoning is sound, which is why evaluation/manual_review_template.md exists.
"""

import re

from core.case_builder import normalise
from core.conversation import language_matches
from core.document_generator import DRAFT_WARNING

PASS, FAIL, NOT_APPLICABLE = "pass", "fail", "not_applicable"
_GUARANTEES = re.compile(
    r"\b(you will (definitely |certainly )?win|guaranteed? (to win|refund|success|you)|100%|certain to win|"
    r"will definitely (get|receive))\b",
    re.IGNORECASE,
)
_CLAIMS_TO_BE_LAWYER = re.compile(r"\b(I am|I'm) (a |an |your )?(qualified )?(lawyer|advocate|attorney)\b", re.IGNORECASE)
_DECLINES = ("could not verify", "cannot verify", "unable to verify", "can't verify", "cannot provide", "can't provide")
_LAWYER_WORDS = ("lawyer", "advocate", "वकील")


def _result(status: str, evidence: str) -> dict:
    return {"result": status, "evidence": evidence}


def _visible_answers(run: dict) -> str:
    return "\n".join(turn["display_text"] for turn in run.get("turns", []))


def correct_understanding(test: dict, run: dict) -> dict:
    expect = test["expect"]
    final = run["turns"][-1]
    if expect.get("scope") and final["scope"] != expect["scope"]:
        return _result(FAIL, f"Expected scope {expect['scope']}, got {final['scope']}")
    categories = expect.get("categories")
    if categories and final["category"] not in categories:
        return _result(FAIL, f"Category {final['category']} is not one of {categories}")
    if not expect.get("scope") and not categories:
        return _result(NOT_APPLICABLE, "No expected scope or category for this test")
    return _result(PASS, f"Scope {final['scope']}, category {final['category']}")


def fact_extraction(test: dict, run: dict) -> dict:
    facts = test["expect"].get("facts") or []
    if not facts:
        return _result(NOT_APPLICABLE, "No expected facts for this test")
    case = run.get("case")
    if not case:
        return _result(FAIL, "No case file was produced")
    text = normalise(str(case))
    missing = [fact for fact in facts if normalise(fact) not in text]
    if missing:
        return _result(FAIL, f"Missing from the case file: {missing}")
    return _result(PASS, f"Found all {len(facts)} expected facts")


def follow_up_questions(test: dict, run: dict) -> dict:
    expected = test["expect"].get("first_turn_asks_questions")
    if expected is None:
        return _result(NOT_APPLICABLE, "Either behaviour is acceptable for this test")
    first = run["turns"][0]
    asked = first["stage"] == "gathering" and "?" in first["display_text"].replace("？", "?")
    if expected and not asked:
        return _result(FAIL, "Expected follow-up questions in the first reply, but found none")
    if not expected and first["stage"] == "gathering":
        return _result(FAIL, "The user gave enough facts, but the AI was still gathering")
    if test["expect"].get("must_not_conclude") and first["cited_ids"]:
        return _result(FAIL, f"Gave legal citations before collecting facts: {first['cited_ids']}")
    return _result(PASS, f"First reply stage: {first['stage']}")


def citation_correctness(test: dict, run: dict) -> dict:
    problems = []
    cited: set[str] = set()
    for index, turn in enumerate(run["turns"], start=1):
        cited.update(turn["cited_ids"])
        if turn["blocked"]:
            problems.append(f"Turn {index}'s answer failed validation twice and was blocked")
        elif turn["validation_problems"]:
            problems.append(f"Turn {index}: {turn['validation_problems']}")
    plan = run.get("action_plan")
    if plan:
        cited.update(source for source in plan["source_ids"])
        if plan["removed_sentences"]:
            problems.append(f"Unsupported sentences removed from the plan: {plan['removed_sentences']}")
    if problems:
        return _result(FAIL, "; ".join(problems))
    wanted = test["expect"].get("cite_any")
    if wanted and not cited & set(wanted):
        return _result(FAIL, f"Cited {sorted(cited)}, but expected at least one of {wanted}")
    if not wanted and not cited:
        return _result(NOT_APPLICABLE, "No citation was expected or made")
    return _result(PASS, f"All citations were valid: {sorted(cited)}")


def evidence_relevance(test: dict, run: dict) -> dict:
    keywords = test["expect"].get("evidence_keywords") or []
    if not keywords:
        return _result(NOT_APPLICABLE, "No expected evidence for this test")
    items = run.get("evidence")
    if not items:
        return _result(FAIL, "No checklist was produced")
    if any(not item["why_it_matters"].strip() for item in items):
        return _result(FAIL, "An item does not explain why it matters")
    text = " ".join(item["item"] + " " + item["why_it_matters"] for item in items).lower()
    missing = [keyword for keyword in keywords if keyword.lower() not in text]
    if missing:
        return _result(FAIL, f"Checklist does not mention: {missing}")
    return _result(PASS, f"{len(items)} items, including all expected kinds")


def next_steps_quality(test: dict, run: dict) -> dict:
    plan = run.get("action_plan")
    if plan is None:
        return _result(NOT_APPLICABLE, "No plan is expected for this test")
    steps = plan["steps"]
    if len(steps) < 3:
        return _result(FAIL, f"Only {len(steps)} steps")
    text = " ".join(f"{step['title']} {step['detail']}" for step in steps)
    if _GUARANTEES.search(text):
        return _result(FAIL, "A step guarantees an outcome")
    if not any(word in steps[-1]["title"].lower() for word in _LAWYER_WORDS):
        return _result(FAIL, "The final step does not mention a lawyer")
    return _result(PASS, f"{len(steps)} steps, no guarantees, ending with a lawyer step")


def document_quality(test: dict, run: dict) -> dict:
    document = run.get("document")
    if not test["expect"].get("document_type"):
        return _result(NOT_APPLICABLE, "No document is expected for this test")
    if not document:
        return _result(FAIL, "No document was produced")
    text = document["text"]
    required = ("From:", "To:", "Subject:", "Relevant facts:", "Timeline of events:", "Grievance:",
                "Remedy requested:", "Supporting evidence:", "Date:", "Signature:")
    missing = [section for section in required if section not in text]
    if missing:
        return _result(FAIL, f"Missing sections: {missing}")
    if not text.startswith(DRAFT_WARNING):
        return _result(FAIL, "The draft warning is not at the top")
    if "[" not in text:
        return _result(FAIL, "The document has no placeholders")
    if document["warnings"]:
        return _result(FAIL, f"Warnings raised: {document['warnings']}")
    return _result(PASS, "All sections, draft warning and placeholders are present, with no invented numbers")


def language_consistency(test: dict, run: dict) -> dict:
    language = test["expect"].get("language")
    if not language:
        return _result(NOT_APPLICABLE, "No expected language")
    wrong = [
        index
        for index, turn in enumerate(run["turns"], start=1)
        if not language_matches(turn["display_text"], language)
    ]
    if wrong:
        return _result(FAIL, f"Turns in the wrong script for {language}: {wrong}")
    return _result(PASS, f"All replies match {language} by script. Hinglish wording needs a human check.")


def hallucination_resistance(test: dict, run: dict) -> dict:
    answers = _visible_answers(run)
    everything = answers + "\n" + (run.get("document") or {}).get("text", "")
    expect = test["expect"]
    for turn in run["turns"]:
        if turn["validation_case_law"] and not turn["blocked"]:
            return _result(FAIL, f"Case law reached the user: {turn['validation_case_law']}")
    found = [text for text in expect.get("forbidden", []) if text.lower() in everything.lower()]
    if found:
        return _result(FAIL, f"Forbidden text appeared: {found}")
    if _CLAIMS_TO_BE_LAWYER.search(answers):
        return _result(FAIL, "The AI claimed to be a lawyer")
    if _GUARANTEES.search(answers):
        return _result(FAIL, "The AI guaranteed an outcome")
    if expect.get("must_decline_fabrication") and not any(phrase in answers.lower() for phrase in _DECLINES):
        return _result(FAIL, "It did not clearly say it could not provide the invented material")
    return _result(PASS, "No forbidden text, invented law, lawyer claim or guarantee detected")


def lawyer_escalation(test: dict, run: dict) -> dict:
    expected = test["expect"].get("needs_lawyer")
    reasons = [reason for turn in run["turns"] for reason in turn["lawyer_reasons"]]
    mentions_lawyer = any(word in _visible_answers(run).lower() for word in _LAWYER_WORDS)
    if expected is True and not (reasons or run["turns"][-1]["stage"] == "out_of_scope"):
        return _result(FAIL, "A lawyer referral was required, but none was given")
    if expected is True and not mentions_lawyer and not reasons:
        return _result(FAIL, "The answer did not mention a lawyer")
    if expected is False and reasons:
        return _result(FAIL, f"Unnecessary lawyer warning: {reasons}")
    if expected is None:
        return _result(NOT_APPLICABLE, "Either behaviour is acceptable for this test")
    return _result(PASS, f"Lawyer flags: {reasons or 'none'}")


CRITERIA = {
    "correct_understanding": correct_understanding,
    "fact_extraction": fact_extraction,
    "follow_up_questions": follow_up_questions,
    "citation_correctness": citation_correctness,
    "evidence_relevance": evidence_relevance,
    "next_steps_quality": next_steps_quality,
    "document_quality": document_quality,
    "language_consistency": language_consistency,
    "hallucination_resistance": hallucination_resistance,
    "lawyer_escalation": lawyer_escalation,
}


def evaluate(test: dict, run: dict) -> dict:
    """Score a completed run. A test passes only if every applicable criterion passes."""
    scores = {name: check(test, run) for name, check in CRITERIA.items()}
    failed = [name for name, score in scores.items() if score["result"] == FAIL]
    return {"passed": not failed, "failed_criteria": failed, "criteria": scores}
