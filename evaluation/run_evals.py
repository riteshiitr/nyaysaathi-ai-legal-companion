"""Runs the test cases through the real pipeline and saves the unedited output.

    python -m evaluation.run_evals              real AI run, saved in raw_outputs/
    python -m evaluation.run_evals --only 1,9   run selected tests only
    python -m evaluation.run_evals --max-usd 3  stop before spending more than about $3
    python -m evaluation.run_evals --resume     keep finished tests, run only the rest
    python -m evaluation.run_evals --pause 10   wait 10 seconds before each AI call
    python -m evaluation.run_evals --mock       scripted run, saved in raw_outputs/mock/

A real run uses your API's free allowance or credit. It never fabricates a result: if
the AI service fails, that test is recorded as an error, and tests that did not run are
recorded as not run. If a free daily limit stops the run, use --resume the next day.
"""

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import RAW_OUTPUTS_DIR, TEST_CASES_FILE, load_settings  # noqa: E402
from core import case_builder, document_generator, evidence_checker, rights  # noqa: E402
from core.ai_engine import AIError, RecordingProvider, get_provider  # noqa: E402
from core.conversation import Conversation  # noqa: E402
from core.legal_retrieval import load_knowledge_base  # noqa: E402
from evaluation.evaluator import evaluate  # noqa: E402
from evaluation.test_report import estimate_usd, write_report  # noqa: E402

DEFAULT_MAX_USD = 5.0
GEMINI_FREE_TIER_PAUSE_SECONDS = 7.0


def _turn_to_dict(turn) -> dict:
    report = turn.report
    return {
        "display_text": turn.display_text,
        "raw_text": turn.text,
        "language": turn.language,
        "stage": turn.stage,
        "scope": turn.scope,
        "category": turn.category,
        "confidence": turn.confidence.value if turn.confidence else None,
        "retrieved_sources": [result.provision.id for result in turn.retrieved],
        "cited_ids": list(report.valid_citations) if report and not turn.blocked else [],
        "validation_problems": report.problems() if report else [],
        "validation_case_law": list(report.case_law_mentions) if report else [],
        "blocked": turn.blocked,
        "correction_attempts": turn.correction_attempts,
        "lawyer_reasons": turn.lawyer_reasons,
        "missing_facts": turn.missing_facts,
    }


def run_test(test: dict, provider: RecordingProvider, knowledge_base) -> dict:
    """Run one test through the same functions the app uses. AI errors propagate to the caller."""
    conversation = Conversation(provider, knowledge_base)
    turns = [_turn_to_dict(conversation.respond(user_message)) for user_message in test["turns"]]
    run: dict = {"turns": turns}

    if turns[-1]["stage"] == "out_of_scope" or test["expect"].get("scope") == "out_of_scope":
        return run
    if test["expect"].get("must_not_conclude"):
        return run

    user_text = conversation.user_text
    case = case_builder.build_case(provider, conversation.transcript(), user_text)
    run["case"] = case
    case_text = case_builder.case_to_text(case)
    language = turns[-1]["language"]

    run["rights_cards"] = [
        {
            "source_id": card.provision.id,
            "how_it_may_relate": card.how_it_may_relate,
            "verification_status": card.verification_status,
            "confidence": card.confidence.value,
        }
        for card in rights.build_rights_cards(provider, knowledge_base, case_text, language)
    ]
    plan = rights.build_action_plan(provider, knowledge_base, case_text, language)
    run["action_plan"] = {
        "steps": plan["steps"],
        "removed_sentences": plan["removed_sentences"],
        "source_ids": [source.id for source in plan["sources"]],
    }
    run["evidence"] = evidence_checker.build_checklist(provider, case_text, user_text, language)

    document_type = test["expect"].get("document_type")
    if document_type:
        document = document_generator.generate_document(
            provider, knowledge_base, document_type, case_text, user_text
        )
        run["document"] = {"type": document_type, "text": document.text, "warnings": document.warnings}
    return run


def finished_record(test: dict, settings, out_dir: Path, run_type: str) -> dict | None:
    """A saved result to reuse, but only if it completed, with the same type of run and models."""
    path = out_dir / f"{test['file']}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    same_models = record.get("model_configured") == {
        "main": settings.model,
        "fast": settings.fast_model,
        "effort": settings.effort,
    }
    usable = record.get("execution_status") == "completed" and record.get("run_type") == run_type and same_models
    return record if usable else None


def execute(test: dict, settings, knowledge_base, out_dir: Path, run_type: str, pause_seconds: float = 0.0) -> dict:
    provider = RecordingProvider(get_provider(settings), pause_seconds=pause_seconds)
    started = datetime.now(timezone.utc).isoformat()
    record = {
        "run_type": run_type,
        "warning": "MOCK: scripted answers, not a real AI result." if run_type == "MOCK" else None,
        "test_id": test["id"],
        "title": test["title"],
        "input_test_case": test,
        "model_configured": {"main": settings.model, "fast": settings.fast_model, "effort": settings.effort},
        "execution_started": started,
    }
    fatal = False
    try:
        run = run_test(test, provider, knowledge_base)
        record.update(execution_status="completed", pipeline_output=run, evaluation=evaluate(test, run))
    except AIError as error:
        record.update(execution_status="error", error_kind=error.kind, error_message=error.user_message)
        fatal = error.kind in ("no_credit", "daily_limit", "auth", "model", "no_key")
    except Exception as error:  # A crash in our code is a test failure to report, not to hide.
        record.update(execution_status="crash", error_kind=type(error).__name__, error_message=str(error))

    record["execution_finished"] = datetime.now(timezone.utc).isoformat()
    record["models_used"] = sorted({call.model for call in provider.calls})
    record["token_usage"] = {
        "input": sum(call.input_tokens or 0 for call in provider.calls),
        "output": sum(call.output_tokens or 0 for call in provider.calls),
    }
    record["estimated_usd"] = estimate_usd(provider.calls)
    record["raw_model_calls"] = provider.calls_as_dicts()
    record["_fatal"] = fatal

    out_dir.mkdir(parents=True, exist_ok=True)
    saved = {key: value for key, value in record.items() if key != "_fatal"}
    (out_dir / f"{test['file']}.json").write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NyaySaathi evaluation suite.")
    parser.add_argument("--mock", action="store_true", help="scripted run, saved separately and labelled MOCK")
    parser.add_argument("--only", help="test numbers to run, such as 1,9,10")
    parser.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help="stop once estimated spend passes this")
    parser.add_argument("--resume", action="store_true", help="keep tests that already finished and run only the rest")
    parser.add_argument("--pause", type=float, help="seconds to wait before each AI call")
    args = parser.parse_args()

    settings = load_settings()
    if args.mock:
        settings = replace(settings, provider="mock")
    if settings.is_mock and not args.mock:
        print("NYAYSAATHI_PROVIDER is set to mock. Use --mock so the output is saved and labelled correctly.")
        return 2
    run_type = "MOCK" if settings.is_mock else "REAL"
    out_dir = RAW_OUTPUTS_DIR / "mock" if settings.is_mock else RAW_OUTPUTS_DIR
    pause = args.pause if args.pause is not None else (GEMINI_FREE_TIER_PAUSE_SECONDS if settings.provider == "gemini" else 0.0)

    cases = json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = {f"test_{int(number):02d}" for number in args.only.split(",")}
        cases = [case for case in cases if case["id"] in wanted]

    knowledge_base = load_knowledge_base()
    records, spent = [], 0.0
    for test in cases:
        saved = finished_record(test, settings, out_dir, run_type) if args.resume else None
        if saved:
            print(f"{test['id']}: already finished, keeping the saved result")
            records.append(saved)
            continue
        if spent >= args.max_usd:
            print(f"{test['id']}: NOT RUN (spending limit of about ${args.max_usd} reached)")
            records.append({"test_id": test["id"], "title": test["title"], "execution_status": "not_run", "reason": "spending limit"})
            continue
        if records and records[-1].get("_fatal"):
            reason = records[-1]["error_message"]
            print(f"{test['id']}: NOT RUN ({reason})")
            records.append({"test_id": test["id"], "title": test["title"], "execution_status": "not_run", "reason": reason, "_fatal": True})
            continue
        print(f"{test['id']}: running {test['title']}...", flush=True)
        record = execute(test, settings, knowledge_base, out_dir, run_type, pause)
        spent += record["estimated_usd"] or 0
        outcome = record["execution_status"]
        if outcome == "completed":
            evaluation = record["evaluation"]
            outcome = "PASS" if evaluation["passed"] else f"FAIL {evaluation['failed_criteria']}"
        else:
            outcome = f"{outcome.upper()}: {record.get('error_message', '')}"
        print(f"  {outcome}  (about ${record['estimated_usd']:.3f})", flush=True)
        records.append(record)

    summary = write_report(records, out_dir, run_type, settings)
    print(f"\n{run_type} RUN: {summary['passed']} passed, {summary['failed']} failed, "
          f"{summary['errors']} errors, {summary['not_run']} not run, of {summary['total_test_cases']}.")
    print(f"About ${summary['estimated_usd_total']:.2f} spent. Report saved in {out_dir / 'TEST_REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
