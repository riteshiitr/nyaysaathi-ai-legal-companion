"""Finds the legal provisions relevant to a user's problem.

Uses BM25, a standard keyword-ranking method, on our small verified knowledge
base. It runs locally, needs no vector database, and its results can be
explained. Each provision carries Hindi and Hinglish keywords, so a query in
any of the three languages can find the same English-language provision.

If nothing relevant is found, search() returns an empty list. Callers must treat
that as "could not verify", never as permission to answer from memory.

Search does not decide whether a problem is in scope. A long story about a
landlord can still share words with refund provisions, so scope is checked
separately by the safety layer.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from config import KNOWLEDGE_BASE_DIR

BM25_K1 = 1.5
BM25_B = 0.75
MIN_SCORE = 2.0  # Below this, a match is too weak to count as relevant.
# In a query of three or more words, one shared word is not enough. Without this,
# "bail application for a murder charge" matches "cancellation charges".
MIN_MATCHED_TERMS_LONG_QUERY = 2
LONG_QUERY_TERMS = 3

STOPWORDS = frozenset(
    """
    a an and are as at be been but by for from had has have he her his i if in into is it its me
    my of on or our she so that the their them they this to was we were what when which who will
    with you your not no do did does can could should would about after again also am any because
    before am out up very
    ka ki ke ko se hai hain tha thi the mera meri mere maine mujhe aur par pe bhi ye yeh wo woh
    kya kyu hua hui ho raha rahi gaya gayi kar kiya
    का की के को से है हैं था थी थे मेरा मेरी मेरे मैंने मुझे और पर भी यह वह क्या हुआ हुई हो रहा रही गया गई कर किया में ने
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Split text into lower-case words, keeping Devanagari vowel signs together."""
    words = re.findall(r"[\wऀ-ॿ]+", text.lower())
    return [_fold_plural(word) for word in words if word not in STOPWORDS]


def _fold_plural(word: str) -> str:
    if word.isascii() and len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    issuer: str
    url: str
    domain: str
    last_verified: str


@dataclass(frozen=True)
class Provision:
    id: str
    document: Document
    ref_type: str  # section, rule, guideline, annexure or procedure
    ref: str
    heading: str
    quote: str
    plain_language: str
    topics: tuple[str, ...]
    keywords: tuple[str, ...]
    extra_quotes: tuple[str, ...] = ()
    in_force_from: date | None = None
    superseded_from: date | None = None

    def is_in_force(self, today: date) -> bool:
        return self.in_force_from is None or today >= self.in_force_from

    def is_superseded(self, today: date) -> bool:
        return self.superseded_from is not None and today >= self.superseded_from

    @property
    def label(self) -> str:
        """Human-readable name, such as 'Section 69, The Consumer Protection Act, 2019'."""
        if self.ref_type == "procedure":
            return f"{self.document.title}: {self.ref}"
        return f"{self.ref_type.capitalize()} {self.ref}, {self.document.title}"


@dataclass(frozen=True)
class SearchResult:
    provision: Provision
    score: float
    not_yet_in_force: bool


@dataclass
class KnowledgeBase:
    documents: dict[str, Document]
    provisions: dict[str, Provision]
    _doc_tokens: dict[str, Counter] = field(default_factory=dict, repr=False)
    _doc_freq: Counter = field(default_factory=Counter, repr=False)
    _avg_len: float = 0.0

    def __post_init__(self) -> None:
        for provision in self.provisions.values():
            # Keywords count twice: they were chosen to describe what the provision is about.
            text = " ".join(
                (
                    provision.heading,
                    provision.plain_language,
                    provision.quote,
                    " ".join(provision.topics).replace("_", " "),
                    " ".join(provision.keywords),
                    " ".join(provision.keywords),
                )
            )
            counts = Counter(tokenize(text))
            self._doc_tokens[provision.id] = counts
            self._doc_freq.update(counts.keys())
        lengths = [sum(counts.values()) for counts in self._doc_tokens.values()]
        self._avg_len = sum(lengths) / len(lengths) if lengths else 0.0

    def _score(self, query_terms: list[str], provision_id: str) -> float:
        counts = self._doc_tokens[provision_id]
        length = sum(counts.values())
        total_docs = len(self._doc_tokens)
        score = 0.0
        for term in set(query_terms):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            doc_freq = self._doc_freq[term]
            idf = math.log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denominator = frequency + BM25_K1 * (1 - BM25_B + BM25_B * length / self._avg_len)
            score += idf * frequency * (BM25_K1 + 1) / denominator
        return score

    def search(
        self,
        query: str,
        top_k: int = 8,
        today: date | None = None,
        domain: str = "consumer",
    ) -> list[SearchResult]:
        """Return the most relevant provisions, best first. May be empty."""
        today = today or date.today()
        query_terms = tokenize(query)
        min_matches = MIN_MATCHED_TERMS_LONG_QUERY if len(set(query_terms)) >= LONG_QUERY_TERMS else 1
        results = []
        for provision in self.provisions.values():
            if provision.document.domain != domain or provision.is_superseded(today):
                continue
            matched = sum(term in self._doc_tokens[provision.id] for term in set(query_terms))
            score = self._score(query_terms, provision.id)
            if score >= MIN_SCORE and matched >= min_matches:
                results.append(SearchResult(provision, score, not provision.is_in_force(today)))
        results.sort(key=lambda result: (-result.score, result.provision.id))
        return results[:top_k]


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def load_knowledge_base(path: Path | None = None) -> KnowledgeBase:
    path = path or KNOWLEDGE_BASE_DIR / "sources.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    documents = {
        item["id"]: Document(
            id=item["id"],
            title=item["title"],
            issuer=item["issuer"],
            url=item["url"],
            domain=item["domain"],
            last_verified=item["last_verified"],
        )
        for item in raw["documents"]
    }
    provisions = {
        item["id"]: Provision(
            id=item["id"],
            document=documents[item["document_id"]],
            ref_type=item["ref_type"],
            ref=item["ref"],
            heading=item["heading"],
            quote=item["quote"],
            plain_language=item["plain_language"],
            topics=tuple(item["topics"]),
            keywords=tuple(item["keywords"]),
            extra_quotes=tuple(item.get("extra_quotes", ())),
            in_force_from=_parse_date(item.get("in_force_from")),
            superseded_from=_parse_date(item.get("superseded_from")),
        )
        for item in raw["provisions"]
    }
    return KnowledgeBase(documents, provisions)


def format_for_prompt(results: list[SearchResult]) -> str:
    """Render retrieved provisions as the source material given to the AI model."""
    if not results:
        return "NO VERIFIED SOURCES WERE FOUND FOR THIS QUESTION."
    blocks = []
    for result in results:
        provision = result.provision
        status = (
            f"NOT YET IN FORCE. Starts on {provision.in_force_from.isoformat()}."
            if result.not_yet_in_force
            else "In force."
        )
        quotes = " | ".join((provision.quote, *provision.extra_quotes))
        blocks.append(
            f"[SRC:{provision.id}]\n"
            f"Source: {provision.label}\n"
            f"Status: {status}\n"
            f"Official wording: {quotes}\n"
            f"Plain explanation: {provision.plain_language}"
        )
    return "\n\n".join(blocks)
