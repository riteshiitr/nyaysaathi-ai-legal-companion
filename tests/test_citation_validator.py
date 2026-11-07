"""Tests for the anti-hallucination checks. These use no AI and no internet."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.citation_validator import (  # noqa: E402
    Confidence,
    remove_unsupported_sentences,
    strip_citation_tags,
    validate,
)
from core.legal_retrieval import load_knowledge_base  # noqa: E402

RETRIEVED = {"CPA2019-S69", "CPA2019-S2-47-viii", "ECOM2020-R4-5", "ECOM2026-R4-5"}


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def test_properly_cited_answer_is_supported(kb):
    text = "You generally have two years to file under Section 69 [SRC:CPA2019-S69]."
    report = validate(text, RETRIEVED, kb)
    assert report.is_clean
    assert report.confidence is Confidence.SUPPORTED


def test_invented_citation_id_is_rejected(kb):
    report = validate("Your refund is guaranteed [SRC:CPA2019-S999].", RETRIEVED, kb)
    assert report.unknown_citations == ["CPA2019-S999"]
    assert report.confidence is Confidence.INSUFFICIENT


def test_real_citation_that_was_not_retrieved_is_rejected(kb):
    report = validate("You may appeal [SRC:CPA2019-S41].", RETRIEVED, kb)
    assert report.unretrieved_citations == ["CPA2019-S41"]
    assert not report.is_clean


def test_invented_section_without_citation_is_rejected(kb):
    report = validate("Section 420 gives you a full refund.", RETRIEVED, kb)
    assert report.uncited_references == ["Section 420"]


def test_real_section_without_citation_is_rejected(kb):
    report = validate("Section 69 gives you two years.", RETRIEVED, kb)
    assert report.uncited_references == ["Section 69"]


def test_citation_that_does_not_match_the_named_section_is_rejected(kb):
    report = validate("Section 35 gives you two years [SRC:CPA2019-S69].", RETRIEVED, kb)
    assert report.uncited_references == ["Section 35"]
    assert report.confidence is Confidence.PARTIAL


def test_citation_in_a_different_sentence_does_not_count(kb):
    text = "You have two years [SRC:CPA2019-S69]. Section 69 also allows late filing."
    assert validate(text, RETRIEVED, kb).uncited_references == ["Section 69"]


@pytest.mark.parametrize(
    "mention, citation",
    [
        ("Section 69(1)", "CPA2019-S69"),
        ("Section 2(47)", "CPA2019-S2-47-viii"),
        ("Section 2(47)(viii)", "CPA2019-S2-47-viii"),
        ("Rule 4(5)", "ECOM2020-R4-5"),
        ("धारा ६९", "CPA2019-S69"),
        ("dhara 69", "CPA2019-S69"),
    ],
)
def test_reference_variants_match_their_citation(kb, mention, citation):
    assert validate(f"Please see {mention} [SRC:{citation}].", RETRIEVED, kb).is_clean


def test_wrong_clause_of_a_section_is_rejected(kb):
    report = validate("Section 2(47)(i) applies [SRC:CPA2019-S2-47-viii].", RETRIEVED, kb)
    assert report.uncited_references == ["Section 2(47)(i)"]


def test_section_number_cannot_borrow_a_rule_citation(kb):
    report = validate("Section 4(5) applies [SRC:ECOM2020-R4-5].", RETRIEVED, kb)
    assert report.uncited_references == ["Section 4(5)"]


@pytest.mark.parametrize(
    "text",
    [
        "In Sharma v. Flipkart the court ordered a refund.",
        "In Ramesh Kumar vs. Amazon Seller Services a refund was ordered.",
        "This is settled by AIR 2019 SC 1234.",
        "See (2020) 5 SCC 100.",
        "The Supreme Court has held that sellers must refund.",
        "सुप्रीम कोर्ट ने कहा है कि रिफंड देना होगा।",
        "Supreme court ne bola hai ki refund milega.",
    ],
)
def test_case_law_is_rejected(kb, text):
    report = validate(text, RETRIEVED, kb)
    assert report.case_law_mentions
    assert not report.is_clean


@pytest.mark.parametrize(
    "text",
    [
        "Compare a refund vs replacement before you decide.",
        "A Replacement vs Refund choice is yours.",
        "The Supreme Court is the highest court in India.",
    ],
)
def test_ordinary_wording_is_not_mistaken_for_case_law(kb, text):
    assert validate(text, RETRIEVED, kb).case_law_mentions == []


def test_abbreviated_section_is_still_checked(kb):
    assert validate("Sec. 420 gives you a refund.", RETRIEVED, kb).uncited_references == ["Sec. 420"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.consumerhelpline.gov.in-fake.com/refund",
        "https://legalblog.example.com/refund",
        "https://notgov.in/consumerhelpline.gov.in",
    ],
)
def test_unofficial_links_are_rejected(kb, url):
    assert validate(f"Read more at {url}", RETRIEVED, kb).unofficial_urls == [url]


def test_official_links_are_accepted(kb):
    text = "File at https://e-jagriti.gov.in/ or https://consumerhelpline.gov.in/. Rules: https://consumeraffairs.gov.in/x.pdf"
    assert validate(text, RETRIEVED, kb).unofficial_urls == []


def test_honestly_declining_an_unverifiable_section_is_not_a_violation(kb):
    text = "I could not verify the exact legal provision Section 420 that you asked about."
    report = validate(text, RETRIEVED, kb)
    assert report.is_clean
    assert report.declined_references == ["Section 420"]
    assert report.confidence is Confidence.INSUFFICIENT


def test_citing_a_rule_not_yet_in_force_is_only_partially_supported(kb):
    text = "From 2027 you also get a copy [SRC:ECOM2026-R4-5]."
    report = validate(text, RETRIEVED, kb, today=date(2026, 11, 6))
    assert report.is_clean
    assert report.confidence is Confidence.PARTIAL
    assert validate(text, RETRIEVED, kb, today=date(2027, 1, 1)).confidence is Confidence.SUPPORTED


def test_answer_without_any_legal_claim_has_insufficient_support(kb):
    assert validate("Please tell me when you bought the phone.", RETRIEVED, kb).confidence is Confidence.INSUFFICIENT


def test_citation_tags_are_removed_for_display():
    assert strip_citation_tags("Two years apply [SRC:CPA2019-S69].") == "Two years apply."


def test_a_year_after_the_word_rules_is_not_a_rule_number(kb):
    assert validate("The E-Commerce Rules 2020 apply to online sales.", RETRIEVED, kb).is_clean


@pytest.mark.parametrize(
    "text",
    [
        "You must file within two years.",
        "The District Commission limit is fifty lakh rupees.",
        "Call the helpline on 1915.",
        "आपको दो साल के भीतर शिकायत करनी होगी।",
    ],
)
def test_sensitive_legal_facts_need_a_citation(kb, text):
    assert validate(text, RETRIEVED, kb).uncited_claims


def test_sensitive_fact_with_a_citation_is_accepted(kb):
    assert validate("You must file within two years [SRC:CPA2019-S69].", RETRIEVED, kb).is_clean


def test_only_the_unsupported_sentence_is_removed(kb):
    text = "Keep your invoice. Section 420 gives a refund. You must file within two years [SRC:CPA2019-S69]."
    cleaned, removed = remove_unsupported_sentences(text, RETRIEVED, kb)
    assert cleaned == "Keep your invoice. You must file within two years [SRC:CPA2019-S69]."
    assert removed == ["Section 420 gives a refund."]
