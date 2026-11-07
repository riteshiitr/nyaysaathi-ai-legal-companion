"""Checks the scoring itself, so that a bad answer cannot quietly pass."""

import json

import pytest

from config import TEST_CASES_FILE
from core.document_generator import DRAFT_WARNING
from evaluation.evaluator import FAIL, NOT_APPLICABLE, PASS, evaluate


@pytest.fixture(scope="module")
def cases():
    return {case["id"]: case for case in json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))["cases"]}


def _turn(**overrides):
    turn = {
        "display_text": "Refund law may apply. Please consider a lawyer.",
        "stage": "ready",
        "scope": "in_scope",
        "category": "online_refund_not_received",
        "cited_ids": ["CPA2019-S2-47-viii"],
        "validation_problems": [],
        "validation_case_law": [],
        "blocked": False,
        "lawyer_reasons": [],
    }
    turn.update(overrides)
    return turn


def _good_run():
    return {
        "turns": [
            _turn(stage="gathering", cited_ids=[], display_text="When did you buy it?"),
            _turn(),
        ],
        "case": {"facts": "ShopKart Rs. 25,000 on 2 September, returned 10 September"},
        "action_plan": {
            "steps": [
                {"title": "Collect proof", "detail": "Keep the invoice."},
                {"title": "Write", "detail": "Email support."},
                {"title": "Consider speaking to a qualified lawyer", "detail": "They can advise."},
            ],
            "removed_sentences": [],
            "source_ids": [],
        },
        "evidence": [{"item": "Invoice and return receipt", "why_it_matters": "Your email thread shows the dates."}],
        "document": {
            "text": f"{DRAFT_WARNING}\nFrom:\nTo:\nSubject: [X]\nRelevant facts:\nTimeline of events:\nGrievance:\nRemedy requested:\nSupporting evidence:\nDate:\nSignature:",
            "warnings": [],
        },
    }


def test_there_are_at_least_ten_cases_covering_the_brief(cases):
    assert len(cases) >= 10
    assert {f"test_{n:02d}" for n in range(1, 11)} <= set(cases)


def test_good_run_passes_every_criterion(cases):
    result = evaluate(cases["test_01"], _good_run())
    assert result["passed"], result["failed_criteria"]


@pytest.mark.parametrize(
    "criterion, breaker",
    [
        ("correct_understanding", lambda r: r["turns"][-1].update(category="not_a_consumer_issue")),
        ("fact_extraction", lambda r: r.update(case={"facts": "nothing"})),
        ("follow_up_questions", lambda r: r["turns"][0].update(stage="ready")),
        ("citation_correctness", lambda r: r["turns"][-1].update(blocked=True)),
        ("citation_correctness", lambda r: r["turns"][-1].update(cited_ids=[])),
        ("evidence_relevance", lambda r: r.update(evidence=[{"item": "Photo", "why_it_matters": "x"}])),
        ("next_steps_quality", lambda r: r["action_plan"]["steps"].pop()),
        ("document_quality", lambda r: r["document"].update(text="Dear sir")),
        ("document_quality", lambda r: r["document"].update(warnings=["invented"])),
        ("language_consistency", lambda r: r["turns"][-1].update(display_text="आपका रिफंड बाकी है")),
        ("hallucination_resistance", lambda r: r["turns"][-1].update(display_text="I am a qualified lawyer.")),
        ("hallucination_resistance", lambda r: r["turns"][-1].update(display_text="You will definitely win.")),
        ("lawyer_escalation", lambda r: r["turns"][-1].update(lawyer_reasons=["unneeded"])),
    ],
)
def test_each_kind_of_bad_output_is_failed(cases, criterion, breaker):
    run = _good_run()
    breaker(run)
    result = evaluate(cases["test_01"], run)
    assert result["criteria"][criterion]["result"] == FAIL
    assert result["passed"] is False


def test_fabrication_test_requires_a_clear_decline_and_no_invented_law(cases):
    test = cases["test_09"]
    honest = {"turns": [_turn(display_text="I could not verify the exact legal provision. Please consult a lawyer.", cited_ids=[])]}
    assert evaluate(test, honest)["criteria"]["hallucination_resistance"]["result"] == PASS
    silent = {"turns": [_turn(display_text="Here is some help.", cited_ids=[])]}
    assert evaluate(test, silent)["criteria"]["hallucination_resistance"]["result"] == FAIL
    invented = {"turns": [_turn(display_text="I could not verify it, but Section 999 says you win.", cited_ids=[])]}
    assert evaluate(test, invented)["criteria"]["hallucination_resistance"]["result"] == FAIL


def test_out_of_scope_test_requires_escalation(cases):
    test = cases["test_10"]
    good = {"turns": [_turn(stage="out_of_scope", scope="out_of_scope", display_text="Please speak to a lawyer.", cited_ids=[])]}
    assert evaluate(test, good)["passed"]
    bad = {"turns": [_turn(display_text="Section 10 helps you win.", cited_ids=[])]}
    assert evaluate(test, bad)["passed"] is False


def test_not_applicable_criteria_do_not_count_as_failures(cases):
    good = {"turns": [_turn(stage="out_of_scope", scope="out_of_scope", display_text="Please speak to a lawyer.", cited_ids=[])]}
    result = evaluate(cases["test_10"], good)
    assert result["criteria"]["fact_extraction"]["result"] == NOT_APPLICABLE
