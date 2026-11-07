"""Checks every legal quote in knowledge_base/sources.json against the official document.

    python scripts/verify_sources.py

It downloads each official document and confirms that each quote appears in it.
Spacing is ignored because PDF text extraction often breaks words apart.
A quote that fails is a real problem: fix it or remove it from the knowledge base.
"""

import html
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import pypdf
import requests

SOURCES = Path(__file__).resolve().parent.parent / "knowledge_base" / "sources.json"
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0"}  # Some government sites refuse other clients.


def normalise(text: str) -> str:
    """Remove differences caused by PDF extraction, not by the wording itself."""
    text = unicodedata.normalize("NFKC", html.unescape(text))
    for old, new in (("“", '"'), ("”", '"'), ("’", "'"), ("‘", "'"), ("—", "-"), ("–", "-")):
        text = text.replace(old, new)
    return re.sub(r"\s+", "", text).lower()


def fetch_text(document: dict) -> str:
    response = requests.get(document["url"], headers=BROWSER_HEADERS, timeout=90)
    response.raise_for_status()
    if document["format"] == "pdf":
        reader = pypdf.PdfReader(io.BytesIO(response.content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    without_code = re.sub(r"<(script|style).*?</\1>", " ", response.text, flags=re.S)
    return re.sub(r"<[^>]+>", " ", without_code)


def main() -> int:
    knowledge_base = json.loads(SOURCES.read_text(encoding="utf-8"))
    texts: dict[str, str] = {}
    for document in knowledge_base["documents"]:
        try:
            texts[document["id"]] = normalise(fetch_text(document))
            print(f"[OK]   Downloaded {document['id']}")
        except Exception as error:  # Report every document rather than stopping at the first.
            print(f"[FAIL] Could not read {document['id']}: {type(error).__name__}: {error}")

    checked = failed = visual = unreachable = 0
    for provision in knowledge_base["provisions"]:
        if provision.get("verification") == "visual_check":
            visual += 1
            print(f"[NOTE] {provision['id']}: read by eye, not checkable by script")
            continue
        text = texts.get(provision["document_id"])
        if text is None:
            unreachable += 1
            continue
        for quote in [provision["quote"], *provision.get("extra_quotes", [])]:
            checked += 1
            if normalise(quote) not in text:
                failed += 1
                print(f"[FAIL] {provision['id']}: not found in source: {quote[:90]}")

    print(
        f"\n{checked - failed} of {checked} quotes matched the official text. "
        f"{visual} checked by eye. {unreachable} provisions skipped because a document was unreachable."
    )
    return 0 if failed == 0 and unreachable == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
