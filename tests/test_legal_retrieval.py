"""Tests for the knowledge base and search. These use no AI and no internet."""

import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.citation_validator import OFFICIAL_DOMAINS  # noqa: E402
from core.legal_retrieval import format_for_prompt, load_knowledge_base  # noqa: E402

TODAY = date(2026, 11, 6)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def found_ids(kb, query, today=TODAY):
    return {result.provision.id for result in kb.search(query, today=today)}


def test_every_source_link_is_official(kb):
    for document in kb.documents.values():
        host = urlparse(document.url).hostname.removeprefix("www.")
        assert host in OFFICIAL_DOMAINS, document.url


def test_every_provision_has_a_quote_and_explanation(kb):
    assert len(kb.provisions) >= 30
    for provision in kb.provisions.values():
        assert provision.quote and provision.plain_language and provision.topics


def test_no_case_law_in_knowledge_base(kb):
    assert not {provision.ref_type for provision in kb.provisions.values()} & {"case", "judgment"}


@pytest.mark.parametrize(
    "query, expected",
    [
        ("My refund has not been received 30 days after I returned the phone", "CPA2019-S2-47-viii"),
        ("seller refusing replacement of a defective product bought online", "ECOM2020-R6-3"),
        ("the company promised a service but failed to provide it", "CPA2019-S2-11"),
        ("I cancelled my subscription but auto debit keeps deducting money", "DARK2023-SUBSCRIPTION-TRAP"),
        ("warranty is valid but the brand will not repair my product", "CPA2019-S84-1"),
        ("the advertisement was false and misleading", "CPA2019-S2-28"),
        ("what is the last date, how many years do I have to file", "CPA2019-S69"),
        ("how much is the fee to file a consumer court complaint", "CDRC2023-R7-FEE"),
        ("which number do I call for the consumer helpline", "NCH-CONTACT"),
    ],
)
def test_english_queries_find_the_right_provision(kb, query, expected):
    assert expected in found_ids(kb, query)


@pytest.mark.parametrize(
    "query, expected",
    [
        ("मैंने ऑनलाइन फोन खरीदा, वह खराब निकला और कंपनी पैसे वापस करने से मना कर रही है", "ECOM2020-R6-3"),
        ("मेरा रिफंड अभी तक नहीं आया", "ECOM2020-R4-10"),
        ("शिकायत दर्ज करने की फीस कितनी है", "CDRC2023-R7-FEE"),
    ],
)
def test_hindi_queries_find_the_right_provision(kb, query, expected):
    assert expected in found_ids(kb, query)


@pytest.mark.parametrize(
    "query, expected",
    [
        ("maine online phone liya tha kharab nikla, seller paisa wapas karne se mana kar raha hai", "ECOM2020-R6-3"),
        ("subscription cancel kiya phir bhi auto debit se paisa kat raha hai", "DARK2023-SUBSCRIPTION-TRAP"),
        ("consumer court me shikayat kaise darj kare", "CPA2019-S35-1"),
    ],
)
def test_hinglish_queries_find_the_right_provision(kb, query, expected):
    assert expected in found_ids(kb, query)


@pytest.mark.parametrize(
    "query",
    [
        "I want a divorce and custody of my children",
        "my landlord is evicting me from the flat",
        "bail application for a murder charge",
        "मुझे तलाक चाहिए",
    ],
)
def test_out_of_scope_questions_find_nothing(kb, query):
    assert kb.search(query, today=TODAY) == []


def test_empty_results_are_labelled_for_the_model():
    assert "NO VERIFIED SOURCES" in format_for_prompt([])


def test_2026_amendment_is_flagged_as_not_yet_in_force_today(kb):
    results = kb.search("grievance officer did not acknowledge within 48 hours one month", today=TODAY)
    by_id = {result.provision.id: result for result in results}
    assert by_id["ECOM2026-R4-5"].not_yet_in_force is True
    assert by_id["ECOM2020-R4-5"].not_yet_in_force is False
    assert "NOT YET IN FORCE" in format_for_prompt([by_id["ECOM2026-R4-5"]])


def test_amendment_replaces_the_old_wording_once_in_force(kb):
    results = kb.search("grievance officer did not acknowledge within 48 hours one month", today=date(2027, 1, 1))
    by_id = {result.provision.id: result for result in results}
    assert "ECOM2020-R4-5" not in by_id
    assert by_id["ECOM2026-R4-5"].not_yet_in_force is False


def test_prompt_format_contains_the_citation_tag_and_official_wording(kb):
    result = next(r for r in kb.search("two years deadline limitation", today=TODAY) if r.provision.id == "CPA2019-S69")
    block = format_for_prompt([result])
    assert "[SRC:CPA2019-S69]" in block
    assert "two years" in block
