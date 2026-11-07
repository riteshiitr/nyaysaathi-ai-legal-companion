"""Checks that this computer is ready to run NyaySaathi.

    python scripts/check_setup.py          free checks only, no API call
    python scripts/check_setup.py --live   also sends two very short messages to the AI

The live check uses a tiny part of your API allowance. The key itself is never printed.
"""

import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PROJECT_ROOT, load_settings  # noqa: E402

REQUIRED_PACKAGES = ("openai", "streamlit", "python-dotenv", "python-docx")
REQUIRED_FOLDERS = (
    "core", "ui", "knowledge_base", "data", "evaluation", "raw_outputs", "deliverables",
)
SECRET_FILES = (".env", ".streamlit/secrets.toml")


def report(passed: bool, message: str) -> bool:
    print(f"[{'PASS' if passed else 'FAIL'}] {message}")
    return passed


def check_python() -> bool:
    version = sys.version_info
    return report(version >= (3, 11), f"Python {version.major}.{version.minor} (3.11 or newer needed)")


def check_packages() -> bool:
    all_found = True
    for package in REQUIRED_PACKAGES:
        try:
            report(True, f"Package {package} {importlib.metadata.version(package)}")
        except importlib.metadata.PackageNotFoundError:
            all_found = report(False, f"Package {package} is missing. Run: pip install -r requirements.txt")
    return all_found


def check_folders() -> bool:
    missing = [name for name in REQUIRED_FOLDERS if not (PROJECT_ROOT / name).is_dir()]
    if missing:
        return report(False, f"Missing folders: {', '.join(missing)}")
    return report(True, "All project folders exist")


def check_secrets_are_ignored() -> bool:
    """Ask git itself whether secret files would be left out of a commit."""
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "check-ignore", *SECRET_FILES],
        capture_output=True,
        text=True,
    )
    ignored = result.stdout.split()
    if result.returncode > 1:
        return report(False, "Could not ask git about secret files. Is this a git repository?")
    if set(ignored) != set(SECRET_FILES):
        return report(False, f"Git would NOT ignore: {set(SECRET_FILES) - set(ignored)}")
    return report(True, "Git will ignore .env and .streamlit/secrets.toml")


def check_api_key_present() -> bool:
    settings = load_settings()
    if settings.has_api_key:
        return report(True, "API key found (value hidden)")
    return report(False, f"No API key found. Add {settings.key_name} to .env (see .env.example).")


def check_live_call() -> bool:
    """Send one short message through the app's own AI connection."""
    from core import prompts
    from core.ai_engine import AIError, get_provider, parse_json

    settings = load_settings()
    report(True, f"Provider: {settings.provider_label}; models: {settings.model} and {settings.fast_model}")
    try:
        provider = get_provider(settings)
        response = provider.complete(
            "Follow the user's instruction.",
            [{"role": "user", "content": "Reply with the single word: ready"}],
            fast=True,
        )
        # The app depends on strict structured answers, so try the real format as well.
        parse_json(
            provider.complete(
                "Classify this consumer complaint.",
                [{"role": "user", "content": "I returned a phone and my refund has not arrived."}],
                schema=prompts.TRIAGE_SCHEMA,
                schema_name="triage",
                fast=True,
            )
        )
    except AIError as error:
        return report(False, error.user_message)
    return report(
        True,
        f"AI replied using {response.model} ({response.input_tokens} input and {response.output_tokens} output tokens), "
        "and returned a valid structured answer",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the NyaySaathi setup.")
    parser.add_argument("--live", action="store_true", help="also send one short message to the AI")
    args = parser.parse_args()

    results = [check_python(), check_packages(), check_folders(), check_secrets_are_ignored()]
    results.append(check_live_call() if args.live else check_api_key_present())

    print(f"\n{sum(results)} of {len(results)} check groups passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
