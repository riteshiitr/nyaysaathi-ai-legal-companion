"""Checks AI-written text against the sources it was given. This is the anti-hallucination layer.

The AI must attach a tag such as [SRC:CPA2019-S69] to each specific legal claim.
This module rejects text that:
  * cites an ID that does not exist, or that was not retrieved for this question;
  * names a section or rule without a matching citation in the same sentence;
  * mentions court cases, since the first version contains no verified case law;
  * states a sensitive legal fact, such as a deadline or fee limit, without a citation;
  * links to a website outside the official list.

The confidence level describes how well the text is sourced. It is NOT a
prediction of winning a case.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from core.legal_retrieval import KnowledgeBase, Provision

UNVERIFIED_STATEMENT = (
    "I could not verify the exact legal provision. "
    "Please consult a qualified lawyer or check the official government source."
)

OFFICIAL_DOMAINS = (
    "indiacode.nic.in",
    "consumeraffairs.nic.in",
    "consumeraffairs.gov.in",
    "consumerhelpline.gov.in",
    "e-jagriti.gov.in",
    "ncdrc.nic.in",
)

CITATION = re.compile(r"\[SRC:([A-Za-z0-9_-]+)\]")

# "Section 69", "Sec. 2(47)(viii)", "Rule 4(5)", "धारा 69", "niyam 4". Devanagari digits are converted first.
LEGAL_REFERENCE = re.compile(
    r"(?<![\wऀ-ॿ])"
    r"(sections?|secs?\.?|s\.|rules?|sub-rules?|धारा|नियम|dhara|niyam)"
    r"\s*(?!(?:19|20)\d{2}\b)(\d+[A-Za-z]?(?:\s*\([0-9a-zA-Z]+\))*)",
    re.IGNORECASE,
)
_RULE_WORDS = ("rule", "sub-rule", "नियम", "niyam")

# Facts people often get wrong. The sentence stating one must carry a citation.
SENSITIVE_CLAIM = re.compile(
    r"\bwithin\s+(?:two|2)\s+years\b|\b(?:two|2)\s+years?\s+(?:to|from|limit)|limitation period"
    r"|\b(?:forty[- ]eight|48)\s+hours\b|\b(?:fifty|50)\s+lakh\b|\b(?:two|2)\s+crore\b"
    r"|\bfiling fee\b|\b1915\b|\b1800114000\b"
    r"|दो साल|2 साल|\bdo saal\b|48 घंटे|50 लाख|2 करोड़|दो करोड़|\b1915\b",
    re.IGNORECASE,
)

# Case names are case-sensitive, so that "refund vs replacement" is not mistaken for a case.
CASE_NAME = re.compile(r"\b[A-Z][\w.&]*(?:\s+[A-Z][\w.&]*)*\s+(?:v\.|vs\.|versus)\s+[A-Z]")
CASE_LAW = re.compile(
    r"\bAIR\s+(?:19|20)\d{2}\b"
    r"|\(\d{4}\)\s*\d+\s*SCC\b"
    r"|\b(?:19|20)\d{2}\s+SCC\b"
    r"|\b(?:Supreme Court|High Court|NCDRC|National Commission)\s+(?:has\s+)?(?:held|ruled|decided)\b"
    r"|सुप्रीम कोर्ट ने|उच्चतम न्यायालय ने|उच्च न्यायालय ने|हाई कोर्ट ने"
    r"|\b(?:supreme court|high court)\s+ne\b",
    re.IGNORECASE,
)

URL = re.compile(r"https?://[^\s)\]>\"']+|\bwww\.[^\s)\]>\"']+", re.IGNORECASE)

# A sentence with one of these honestly declines to confirm the reference it mentions.
DECLINE_PHRASES = (
    "could not verify",
    "cannot verify",
    "can't verify",
    "unable to verify",
    "सत्यापित नहीं",
    "पुष्टि नहीं कर",
    "verify nahi",
)

# Full stops after "v.", "vs." and "Sec." do not end a sentence.
SENTENCE_END = re.compile(
    r"(?<=[.!?।])(?<!\bv\.)(?<!\bvs\.)(?<!\bsec\.)(?<!\bsecs\.)(?<!\bs\.)\s+|\n+",
    re.IGNORECASE,
)
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


class Confidence(str, Enum):
    SUPPORTED = "Supported by verified source"
    PARTIAL = "Partially supported – further verification needed"
    INSUFFICIENT = "Insufficient information – consult a lawyer"


@dataclass
class ValidationReport:
    valid_citations: list[str] = field(default_factory=list)
    unknown_citations: list[str] = field(default_factory=list)
    unretrieved_citations: list[str] = field(default_factory=list)
    uncited_references: list[str] = field(default_factory=list)
    uncited_claims: list[str] = field(default_factory=list)
    case_law_mentions: list[str] = field(default_factory=list)
    unofficial_urls: list[str] = field(default_factory=list)
    declined_references: list[str] = field(default_factory=list)
    not_yet_in_force_citations: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when nothing in the text is unsupported."""
        return not (
            self.unknown_citations
            or self.unretrieved_citations
            or self.uncited_references
            or self.uncited_claims
            or self.case_law_mentions
            or self.unofficial_urls
        )

    def problems(self) -> list[str]:
        """Plain descriptions of what is wrong, used to ask the AI to correct its answer."""
        groups = (
            ("Citation IDs that do not exist", self.unknown_citations),
            ("Citation IDs that are not in the sources provided", self.unretrieved_citations),
            ("Sections or rules named without a matching citation in the same sentence", self.uncited_references),
            ("Legal facts stated without a citation in the same sentence", self.uncited_claims),
            ("Court cases, which you must not mention", self.case_law_mentions),
            ("Links that are not official", self.unofficial_urls),
        )
        return [f"{label}: {', '.join(items)}" for label, items in groups if items]

    @property
    def confidence(self) -> Confidence:
        if not self.valid_citations:
            return Confidence.INSUFFICIENT
        if self.is_clean and not self.not_yet_in_force_citations:
            return Confidence.SUPPORTED
        return Confidence.PARTIAL


def _normalise_ref(ref: str) -> str:
    return re.sub(r"\s+", "", ref).lower()


def _ref_matches(mentioned: str, provision: Provision) -> bool:
    """Does a mentioned reference fall within, or contain, this provision's reference?

    "69" and "69(1)" both match a provision stored as "69". "2(47)" matches
    "2(47)(viii)". "2(47)(i)" does not, because clause (i) is a different clause.
    """
    stored = _normalise_ref(provision.ref)
    return (
        mentioned == stored
        or stored.startswith(mentioned + "(")
        or mentioned.startswith(stored + "(")
    )


def _is_rule_word(word: str) -> bool:
    return word.lower().startswith(_RULE_WORDS)


def _expected_ref_type(word: str) -> str:
    return "rule" if _is_rule_word(word) else "section"


def _is_official(url: str) -> bool:
    host = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/")[0].lower()
    host = host.removeprefix("www.").rstrip(".,;:")
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)


def validate(
    text: str,
    retrieved_ids: set[str],
    knowledge_base: KnowledgeBase,
    today: date | None = None,
) -> ValidationReport:
    """Check text against the provisions retrieved for this question."""
    today = today or date.today()
    report = ValidationReport()
    text = text.translate(_DEVANAGARI_DIGITS)

    cited_ids = list(dict.fromkeys(CITATION.findall(text)))
    for citation in cited_ids:
        if citation not in knowledge_base.provisions:
            report.unknown_citations.append(citation)
        elif citation not in retrieved_ids:
            report.unretrieved_citations.append(citation)
        else:
            report.valid_citations.append(citation)
            if not knowledge_base.provisions[citation].is_in_force(today):
                report.not_yet_in_force_citations.append(citation)

    for sentence in SENTENCE_END.split(text):
        declines = any(phrase in sentence.lower() for phrase in DECLINE_PHRASES)
        cited_here = [
            knowledge_base.provisions[citation]
            for citation in CITATION.findall(sentence)
            if citation in report.valid_citations
        ]

        for match in LEGAL_REFERENCE.finditer(sentence):
            mention = match.group(0).strip()
            if declines:
                report.declined_references.append(mention)
                continue
            mentioned_ref = _normalise_ref(match.group(2))
            expected_type = _expected_ref_type(match.group(1))
            supported = any(
                provision.ref_type == expected_type and _ref_matches(mentioned_ref, provision)
                for provision in cited_here
            )
            if not supported:
                report.uncited_references.append(mention)

        if not declines:
            if not cited_here:
                report.uncited_claims.extend(m.group(0).strip() for m in SENSITIVE_CLAIM.finditer(sentence))
            for pattern in (CASE_NAME, CASE_LAW):
                report.case_law_mentions.extend(m.group(0).strip() for m in pattern.finditer(sentence))

    report.unofficial_urls = [url for url in URL.findall(text) if not _is_official(url)]
    return report


def split_sentences(text: str) -> list[str]:
    return [sentence for sentence in SENTENCE_END.split(text) if sentence.strip()]


def remove_unsupported_sentences(
    text: str,
    retrieved_ids: set[str],
    knowledge_base: KnowledgeBase,
    today: date | None = None,
) -> tuple[str, list[str]]:
    """Delete only the sentences that fail validation. Returns the text and what was removed."""
    kept_lines, removed = [], []
    for line in text.split("\n"):
        kept = []
        for sentence in split_sentences(line):
            if validate(sentence, retrieved_ids, knowledge_base, today).is_clean:
                kept.append(sentence)
            else:
                removed.append(sentence)
        if kept or not line.strip():
            kept_lines.append(" ".join(kept))
    return "\n".join(kept_lines).strip(), removed


def strip_citation_tags(text: str) -> str:
    """Remove [SRC:...] tags for display. The UI shows sources as cards instead."""
    return re.sub(r"[ \t]*\[SRC:[A-Za-z0-9_-]+\]", "", text)
