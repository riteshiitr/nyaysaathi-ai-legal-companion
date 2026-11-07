"""Writes the evaluation summary and report from recorded results, without changing them."""

import json
from datetime import datetime, timezone
from pathlib import Path

# Standard prices per 1M tokens (input, output), read from OpenAI's pricing page on 2026-11-07.
# These are used only to estimate spending.
PRICE_PER_MILLION = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5-mini": (0.25, 2.00),
}
_FALLBACK_PRICE = PRICE_PER_MILLION["gpt-5.5"]  # Unknown models are estimated high, to stay cautious.


def estimate_usd(calls) -> float:
    total = 0.0
    for call in calls:
        if call.is_mock or call.provider == "gemini":  # This project uses Gemini's free tier.
            continue
        price = next((p for name, p in sorted(PRICE_PER_MILLION.items(), key=lambda i: -len(i[0])) if call.model.startswith(name)), _FALLBACK_PRICE)
        total += (call.input_tokens or 0) * price[0] / 1_000_000
        total += (call.output_tokens or 0) * price[1] / 1_000_000
    return round(total, 4)


def summarise(records: list[dict], run_type: str, settings) -> dict:
    completed = [record for record in records if record["execution_status"] == "completed"]
    passed = [record for record in completed if record["evaluation"]["passed"]]

    criterion_totals: dict[str, dict] = {}
    for record in completed:
        for name, score in record["evaluation"]["criteria"].items():
            totals = criterion_totals.setdefault(name, {"pass": 0, "fail": 0, "not_applicable": 0})
            totals[score["result"]] += 1

    # Every citation that reached the user, and every one the checker had to catch first.
    citations_shown, citations_rejected, blocked_answers, corrected_answers = 0, 0, 0, 0
    for record in completed:
        for turn in record["pipeline_output"]["turns"]:
            citations_shown += len(turn["cited_ids"])
            citations_rejected += len(turn["validation_problems"])
            blocked_answers += int(turn["blocked"])
            corrected_answers += int(turn["correction_attempts"] > 0)

    scope_tests = [r for r in completed if r["input_test_case"]["expect"].get("scope") == "out_of_scope"]
    scope_correct = [r for r in scope_tests if r["evaluation"]["criteria"]["correct_understanding"]["result"] == "pass"]
    failures = [
        {
            "test": record["test_id"],
            "title": record["title"],
            "failed_criteria": {
                name: record["evaluation"]["criteria"][name]["evidence"]
                for name in record["evaluation"]["failed_criteria"]
            },
        }
        for record in completed
        if not record["evaluation"]["passed"]
    ]

    return {
        "run_type": run_type,
        "warning": "MOCK: scripted answers. These numbers say nothing about real AI quality." if run_type == "MOCK" else None,
        "generated": datetime.now(timezone.utc).isoformat(),
        "models": {"main": settings.model, "fast": settings.fast_model, "effort": settings.effort},
        "total_test_cases": len(records),
        "passed": len(passed),
        "failed": len(completed) - len(passed),
        "errors": sum(record["execution_status"] in ("error", "crash") for record in records),
        "not_run": sum(record["execution_status"] == "not_run" for record in records),
        "criterion_totals": criterion_totals,
        "citations": {
            "shown_to_users_after_validation": citations_shown,
            "answers_needing_correction": corrected_answers,
            "answers_blocked": blocked_answers,
            "note": "Checks that citations exist and match retrieved sources, not that the legal reasoning is right.",
        },
        "unsupported_scope_handling": {"tests": len(scope_tests), "handled_correctly": len(scope_correct)},
        "observed_failures": failures,
        "errors_detail": [
            {"test": r["test_id"], "status": r["execution_status"], "message": r.get("error_message") or r.get("reason")}
            for r in records
            if r["execution_status"] in ("error", "crash", "not_run")
        ],
        "manual_legal_review": "NOT DONE. See evaluation/manual_review_template.md.",
        "estimated_usd_total": round(sum(record.get("estimated_usd") or 0 for record in records), 4),
        "token_usage": {
            "input": sum(record.get("token_usage", {}).get("input", 0) for record in records),
            "output": sum(record.get("token_usage", {}).get("output", 0) for record in records),
        },
        "results": [
            {
                "test": record["test_id"],
                "title": record["title"],
                "status": record["execution_status"],
                "passed": record["evaluation"]["passed"] if record["execution_status"] == "completed" else None,
            }
            for record in records
        ],
    }


def to_markdown(summary: dict) -> str:
    lines = [f"# NyaySaathi test report ({summary['run_type']} run)", ""]
    if summary["run_type"] == "MOCK":
        lines += [
            "> **MOCK RUN. Do not submit this as a result.** The AI was replaced with scripted answers, so this",
            "> only shows that the test framework runs. It says nothing about real answer quality.",
            "",
        ]
    lines += [
        f"Generated: {summary['generated']}  ",
        f"Models: {summary['models']['main']} and {summary['models']['fast']}, effort {summary['models']['effort']}  ",
        f"Estimated cost: ${summary['estimated_usd_total']:.2f}",
        "",
        "## Totals",
        "",
        "| Total | Passed | Failed | Errors | Not run |",
        "| --- | --- | --- | --- | --- |",
        f"| {summary['total_test_cases']} | {summary['passed']} | {summary['failed']} | {summary['errors']} | {summary['not_run']} |",
        "",
        "## Results by test",
        "",
        "| Test | Title | Result |",
        "| --- | --- | --- |",
    ]
    for result in summary["results"]:
        status = {True: "PASS", False: "FAIL"}.get(result["passed"], result["status"].upper())
        lines.append(f"| {result['test']} | {result['title']} | {status} |")
    lines += ["", "## Results by criterion", "", "| Criterion | Pass | Fail | Not applicable |", "| --- | --- | --- | --- |"]
    for name, totals in summary["criterion_totals"].items():
        lines.append(f"| {name.replace('_', ' ')} | {totals['pass']} | {totals['fail']} | {totals['not_applicable']} |")
    citations = summary["citations"]
    lines += [
        "",
        "## Legal citations",
        "",
        f"- Citations shown to users after validation: {citations['shown_to_users_after_validation']}",
        f"- Answers that needed correction: {citations['answers_needing_correction']}",
        f"- Answers blocked: {citations['answers_blocked']}",
        f"- {citations['note']}",
        "",
        "## Unsupported-scope handling",
        "",
        f"{summary['unsupported_scope_handling']['handled_correctly']} of {summary['unsupported_scope_handling']['tests']} tests handled correctly.",
        "",
        "## Important observed failures",
        "",
    ]
    if summary["observed_failures"]:
        for failure in summary["observed_failures"]:
            lines.append(f"### {failure['test']}: {failure['title']}")
            lines.extend(f"- **{name.replace('_', ' ')}:** {evidence}" for name, evidence in failure["failed_criteria"].items())
            lines.append("")
    else:
        lines += ["None detected by the automated checks.", ""]
    if summary["errors_detail"]:
        lines += ["## Errors and tests not run", ""]
        lines.extend(f"- {item['test']} ({item['status']}): {item['message']}" for item in summary["errors_detail"])
        lines.append("")
    lines += ["## Manual legal review", "", summary["manual_legal_review"], ""]
    return "\n".join(lines)


def write_report(records: list[dict], out_dir: Path, run_type: str, settings) -> dict:
    summary = summarise(records, run_type, settings)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "TEST_REPORT.md").write_text(to_markdown(summary), encoding="utf-8")
    return summary
