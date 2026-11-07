"""Spots situations that need a human lawyer. These rules run without any AI.

The AI's triage also looks for these situations. This module is the backstop: it
still works if the AI misses something, is manipulated, or is unavailable. It
errs on the side of suggesting a lawyer.
"""

import re
from dataclasses import dataclass, field

CRIMINAL = "criminal"
LITIGATION = "litigation"
URGENT = "urgent_deadline"
HIGH_VALUE = "high_value"
OUT_OF_SCOPE = "out_of_scope"
HARM = "physical_harm"

# District Commission's limit under the 2021 Jurisdiction Rules. Above it, a lawyer's help is advised.
HIGH_VALUE_RUPEES = 5_000_000

_PATTERNS = {
    CRIMINAL: (
        r"\b(fraud|scam|scammed|cheated|forged|forgery|fake call|hacked|otp|phishing|cyber ?crime|"
        r"extort\w*|blackmail\w*|threat\w*|police|fir|arrest\w*|dhokha|dhokhadhadi|thagi|thag|dhamki)\b"
        r"|धोखा|धोखाधड़ी|ठगी|ठग|धमकी|पुलिस|एफआईआर|गिरफ्तार"
    ),
    LITIGATION: (
        r"\b(court case|already filed|pending case|summons|legal notice|received a notice|sued|suing|"
        r"writ|appeal|high court|supreme court|arbitration|class action)\b"
        r"|समन|कानूनी नोटिस|मुकदमा|अपील|हाई कोर्ट|सुप्रीम कोर्ट"
    ),
    URGENT: (
        r"\b(hearing (is )?(tomorrow|today|next week)|last date|deadline (is )?(tomorrow|today)|"
        r"limitation (is )?(ending|expiring)|expires? (tomorrow|today)|kal (hi )?(sunwai|hearing)|"
        r"almost two years|nearly two years|more than two years|over two years)\b"
        r"|कल सुनवाई|आखिरी तारीख|अंतिम तिथि"
    ),
    OUT_OF_SCOPE: (
        r"\b(divorce|custody|alimony|talaq|talak|domestic violence|dowry|landlord|tenant|eviction|evict\w*|"
        r"rent agreement|property dispute|land dispute|will and testament|inheritance|bail|murder|rape|assault|"
        r"salary|wrongful termination|fired from|employer|income tax|gst notice|immigration|visa)\b"
        r"|तलाक|गुजारा भत्ता|दहेज|घरेलू हिंसा|मकान मालिक|किरायेदार|जमीन विवाद|संपत्ति विवाद|जमानत|हत्या|बलात्कार|वेतन|नौकरी से निकाला"
    ),
    HARM: (
        r"\b(injured|injury|hospitali[sz]ed|burn(ed|t)|explod\w*|electric shock|poison\w*|food poisoning|died|death)\b"
        r"|घायल|चोट|अस्पताल|जल गया|फट गया|मौत"
    ),
}
_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _PATTERNS.items()}

_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹|rupees?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|लाख|crores?|करोड़)", re.IGNORECASE
)
_PLAIN_AMOUNT = re.compile(r"(?:rs\.?|inr|₹|rupees?)\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_MULTIPLIERS = {"lakh": 100_000, "lac": 100_000, "लाख": 100_000, "crore": 10_000_000, "करोड़": 10_000_000}

REASON_TEXT = {
    CRIMINAL: "This may involve suspected criminal activity. Consider the police or cybercrime authorities and a lawyer.",
    LITIGATION: "This appears to involve an existing or complex legal proceeding, which needs a lawyer.",
    URGENT: "A deadline may be close. Please speak to a lawyer as soon as possible.",
    HIGH_VALUE: "The amount involved appears to be large, so please get a lawyer's advice.",
    OUT_OF_SCOPE: "This appears to be outside consumer disputes, which is all NyaySaathi covers.",
    HARM: "This may involve physical harm. Please seek medical help if needed, and speak to a lawyer.",
}


@dataclass
class SafetyAssessment:
    flags: list[str] = field(default_factory=list)

    @property
    def needs_lawyer(self) -> bool:
        return bool(self.flags)

    @property
    def reasons(self) -> list[str]:
        return [REASON_TEXT[flag] for flag in self.flags]


def largest_amount_rupees(text: str) -> int:
    """Find the largest rupee amount mentioned. Used only to suggest a lawyer."""
    amounts = [0]
    for number, unit in _AMOUNT.findall(text):
        multiplier = next((v for k, v in _MULTIPLIERS.items() if unit.lower().startswith(k)), 1)
        amounts.append(int(float(number.replace(",", "")) * multiplier))
    amounts.extend(int(float(number.replace(",", ""))) for number in _PLAIN_AMOUNT.findall(text))
    return max(amounts)


def assess(text: str) -> SafetyAssessment:
    """Check text for situations that call for a human lawyer."""
    flags = [name for name, pattern in _COMPILED.items() if pattern.search(text)]
    if largest_amount_rupees(text) > HIGH_VALUE_RUPEES:
        flags.append(HIGH_VALUE)
    return SafetyAssessment(flags)
