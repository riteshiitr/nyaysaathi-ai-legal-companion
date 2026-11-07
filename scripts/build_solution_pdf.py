"""Builds deliverables/NyaySaathi_Solution_Document.pdf (maximum two pages).

    python scripts/build_solution_pdf.py

The results section is filled in from raw_outputs/evaluation_summary.json, so the
document cannot claim more than was measured. Run the evaluation first, then this.
Mock results are never used. Without a real run, the PDF says that results are pending.
"""

import json
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "deliverables" / "NyaySaathi_Solution_Document.pdf"
SUMMARY = ROOT / "raw_outputs" / "evaluation_summary.json"
SOURCES = ROOT / "knowledge_base" / "sources.json"

NAVY = colors.HexColor("#0F172A")
BLUE = colors.HexColor("#1D4ED8")
SOFT = colors.HexColor("#EFF6FF")
LINE = colors.HexColor("#CBD5E1")
RED = colors.HexColor("#991B1B")

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=8.1, leading=10.2, textColor=NAVY, spaceAfter=2)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=8, bulletIndent=0, spaceAfter=1)
HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=9.4, leading=11, textColor=BLUE, spaceBefore=5, spaceAfter=1.5)
TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=15, leading=17, textColor=NAVY)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=8.6, textColor=colors.HexColor("#475569"), spaceAfter=3)
BOX = ParagraphStyle("box", parent=BODY, fontSize=7.1, leading=8.3, alignment=TA_CENTER, spaceAfter=0)
WARN = ParagraphStyle("warn", parent=BODY, fontName="Helvetica-Bold", textColor=RED, spaceAfter=3)


def real_results() -> dict | None:
    if not SUMMARY.exists():
        return None
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    # A run in which no test finished, such as when credit has run out, gives no results to report.
    completed = summary.get("passed", 0) + summary.get("failed", 0)
    return summary if summary.get("run_type") == "REAL" and completed > 0 else None


def flow_diagram() -> Table:
    steps = [
        "<b>User</b><br/>English, Hindi, Hinglish; typed or spoken",
        "<b>Safety rules + AI triage</b><br/>scope, stage, lawyer flags",
        "<b>Retrieve</b><br/>BM25 search of verified provisions",
        "<b>Generate</b><br/>LLM must tag each legal claim with a source",
        "<b>Validate (code)</b><br/>retry once, then block",
        "<b>Output</b><br/>answer, case, rights cards, plan, documents",
    ]
    cells, widths = [], []
    for index, step in enumerate(steps):
        cells.append(Paragraph(step, BOX))
        widths.append(28 * mm)
        if index < len(steps) - 1:
            cells.append(Paragraph("<b>&gt;</b>", BOX))
            widths.append(3.5 * mm)
    table = Table([cells], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    for column in range(0, len(cells), 2):
        style += [("BOX", (column, 0), (column, 0), 0.6, BLUE), ("BACKGROUND", (column, 0), (column, 0), SOFT)]
    table.setStyle(TableStyle(style))
    return table


def results_section(summary: dict | None) -> list:
    if summary is None:
        return [
            Paragraph(
                "RESULTS PENDING: the real evaluation has not run yet. Do not submit this version.",
                WARN,
            ),
            Paragraph(
                "The framework is built: 12 synthetic cases, scored on 10 criteria with automated assertions, "
                "structured-output validation and citation checks. A scripted mock run confirmed that the framework "
                "works and that poor answers fail. It says nothing about real answer quality. Mock outputs are stored "
                "separately and labelled MOCK. Code-level tests cover the validator, retrieval, safety rules, case "
                "checks and user interface flows without any AI.",
                BODY,
            ),
        ]

    totals = summary["criterion_totals"]
    rows = [["Criterion", "Pass", "Fail", "n/a"]] + [
        [name.replace("_", " ").capitalize(), value["pass"], value["fail"], value["not_applicable"]]
        for name, value in totals.items()
    ]
    half = (len(rows) + 1) // 2
    table = Table(
        [
            left + right
            for left, right in zip(
                rows[: half + 1],
                [rows[0]] + rows[half + 1 :] + [["", "", "", ""]] * (half + 1),
            )
        ],
        colWidths=[46 * mm, 9 * mm, 9 * mm, 9 * mm] * 2,
    )
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 0.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
            ]
        )
    )
    citations = summary["citations"]
    scope = summary["unsupported_scope_handling"]
    return [
        Paragraph(
            f"<b>Real run on {summary['generated'][:10]} with {summary['models']['main']} and {summary['models']['fast']}:</b> "
            f"{summary['total_test_cases']} test cases: {summary['passed']} passed, {summary['failed']} failed, "
            f"{summary['errors']} errors, {summary['not_run']} not run. A test passes only if every applicable criterion passes. "
            f"Citations shown after validation: {citations['shown_to_users_after_validation']}; answers needing correction: "
            f"{citations['answers_needing_correction']}; answers blocked: {citations['answers_blocked']}. Unsupported scope handled "
            f"correctly: {scope['handled_correctly']} of {scope['tests']}. Estimated cost: US${summary['estimated_usd_total']:.2f}. "
            "Citation checks confirm that sources exist and match. They do not prove the legal reasoning is right. "
            f"Manual legal review: {summary['manual_legal_review']}",
            BODY,
        ),
        table,
        Spacer(1, 2),
    ]


def observed_failures(summary: dict | None) -> list:
    if not summary or not summary["observed_failures"]:
        return []
    parts = []
    for failure in summary["observed_failures"][:5]:
        names = ", ".join(name.replace("_", " ") for name in failure["failed_criteria"])
        parts.append(f"{failure['test']} ({names})")
    extra = len(summary["observed_failures"]) - len(parts)
    suffix = f", and {extra} more" if extra > 0 else ""
    return [Paragraph(f"<b>Observed in the test run:</b> {'; '.join(parts)}{suffix}. Details are in raw_outputs/TEST_REPORT.md.", BODY)]


def bullets(*items: str) -> list:
    return [Paragraph(item, BULLET, bulletText="-") for item in items]


def story(summary: dict | None, kb: dict) -> list:
    documents, provisions = len(kb["documents"]), len(kb["provisions"])
    return [
        Paragraph("NyaySaathi: Your AI Legal Companion", TITLE),
        Paragraph("Solution document. Understand Your Rights. Know Your Options. Take Action.", SUB),
        Paragraph("1. Problem selected and why", HEAD),
        Paragraph(
            "People with a consumer dispute often cannot afford immediate legal help, do not know the terminology or the channels, "
            "and give up. I narrowed the broad brief of an \"AI lawyer for India\" to consumer disputes and refund complaints. "
            "A narrow domain lets the law be verified properly, and it is better to be reliable in one area than plausible in all of them. "
            "Its disputes are also document-driven, so organised facts and a draft letter are directly useful.",
            BODY,
        ),
        Paragraph("2. Target users and assumptions", HEAD),
        Paragraph(
            "Ordinary Indian consumers, including those more comfortable in Hindi or Hinglish, who have never used a legal service or a "
            "chatbot. I assume they have a phone or computer, can review a draft before using it, and may not have all their documents ready. "
            "Where the brief was open, I assumed: one legal area done reliably beats many done loosely; no accounts or saved cases in a prototype; "
            "and test data should be synthetic, because the free AI tier may use what it receives.",
            BODY,
        ),
        Paragraph("3. Scope and limitations", HEAD),
        Paragraph(
            f"In scope: refunds, defects, cancellations, wrong charges, warranty, misleading advertisements and failed services. "
            f"Out of scope: family, property, employment, tax and criminal matters, which are referred to a lawyer. It gives legal "
            f"information and not advice. It never files or sends anything. It cites no case law. The knowledge base is a selection of "
            f"{provisions} provisions, not all of consumer law, and <b>no qualified lawyer has reviewed it</b>.",
            BODY,
        ),
        Paragraph("4. How the application works", HEAD),
        Paragraph(
            "The user explains the problem by text or voice. The assistant asks follow-up questions until key facts are known, then explains "
            "options with sources. Build My Case produces an editable file that labels each fact as user-provided, AI inference or unverified. "
            "Know My Rights gives legal information cards and a step-by-step plan. The app also creates an evidence checklist and five draft "
            "documents (TXT or DOCX, always marked as drafts), and offers a labelled practice mode with feedback.",
            BODY,
        ),
        Paragraph("5. AI architecture and technology choices", HEAD),
        flow_diagram(),
        Spacer(1, 3),
        Paragraph(
            "Python and Streamlit keep deployment simple. Google Gemini's free tier provides the models, with strict JSON schemas for structured "
            "outputs and a lighter model for classification. <b>The model is a settings change:</b> .env selects Gemini, OpenAI or any OpenAI-style API, "
            "including one a company provides, and provider code sits in one module. <b>Paid option, not used:</b> a stronger model could improve Hindi and "
            "legal reasoning, connected the same way, and the evaluation can compare the two. Retrieval is local BM25 with Hindi and Hinglish keywords: for a small curated corpus, it is explainable, needs no vector database, "
            "and returns nothing when nothing matches. UI, conversation, retrieval, prompts, case extraction, documents and evaluation are separate modules.",
            BODY,
        ),
        Paragraph("6. How legal hallucination is prevented", HEAD),
        *bullets(
            f"<b>Verified corpus:</b> {provisions} provisions from {documents} official documents. A script re-downloads each document and "
            "confirms that every quote appears in it. Effective dates are stored: a 2026 e-commerce amendment is flagged as not in force until 1 January 2027.",
            "<b>Grounded generation:</b> only retrieved provisions are supplied, and each legal claim must carry a source tag.",
            "<b>Code validation, not trust:</b> rejects unknown or unretrieved citations, section numbers without a matching citation in the same "
            "sentence, uncited deadlines, limits and helpline numbers, case-law patterns and unofficial links. One corrected retry is allowed; "
            "after that, the answer is blocked and the user sees \"I could not verify the exact legal provision\".",
            "<b>Facts too:</b> a fact marked as user-stated must quote the user's words, and numbers absent from the conversation are flagged.",
            "<b>Confidence label:</b> describes sourcing only (supported, partial or insufficient), and never a chance of winning.",
            "<b>Safety rules:</b> rule-based checks for crime, urgency, litigation, harm, high value and scope still work if the AI is wrong or manipulated.",
        ),
        Paragraph("7. Division of work between AI, code and human review", HEAD),
        *bullets(
            "<b>AI at run time:</b> understands the story, asks questions, extracts facts, explains in plain language and drafts documents. It is treated as untrusted.",
            "<b>Code at run time:</b> search, citation and fact checks, safety rules, draft labels, exports and legal text on cards, which comes from the knowledge base and not the model.",
            "<b>Human:</b> the user reviews and edits everything before use. A manual legal-quality review template exists, and that review has not yet been done.",
            "<b>AI tools I used:</b> I scoped the product and directed its build; Claude Code in VS Code wrote much of the code and collected sources. "
            "<b>Where it got it wrong:</b> its first citation checker let an invented case, \"Sharma v. Flipkart\", through. Testing caught this, and it now has its own test. "
            "It also told me to buy API credit, which the brief says is unnecessary, so I moved to a free tier.",
        ),
        Paragraph("8. Scaling to other legal domains and many users", HEAD),
        Paragraph(
            "<b>Domains:</b> provisions carry a domain field, so adding one means adding verified sources, keywords, scope rules, prompts and test cases, without "
            "rebuilding the pipeline. <b>Users:</b> session data is kept in memory and nothing is stored. For large numbers of users, I would move the core modules "
            "behind an API service, run instances horizontally, add caching, rate limits and a queue, add semantic search as the corpus grows, and schedule source "
            "verification to detect legal changes. These scaling steps are designs and have not been built or load-tested.",
            BODY,
        ),
        Paragraph("9. Quality evaluation and test results", HEAD),
        *results_section(summary),
        Paragraph("10. Known failure cases and future improvements", HEAD),
        *observed_failures(summary),
        *bullets(
            "<b>Validator limits:</b> it matches patterns. A wrong legal claim in plain words, with a real citation attached, can pass. Only human review can catch this.",
            "<b>Retrieval limits:</b> keyword search can miss paraphrases, and a long out-of-scope story can match consumer provisions, so scope relies on triage and rules.",
            "<b>Knowledge gaps:</b> no RBI refund timelines or Ombudsman, and whether an advocate is needed on e-Jagriti is unverified. Later changes to the law are not detected automatically.",
            "<b>Language:</b> checks confirm the script only, so Hindi and Hinglish quality needs human review. Documents are drafted in English by default.",
            "<b>Not included:</b> reading uploaded documents, and saved cases. <b>Next:</b> lawyer review, wider sources, semantic search, automatic source monitoring and user testing.",
        ),
    ]


def main() -> int:
    summary = real_results()
    kb = json.loads(SOURCES.read_text(encoding="utf-8"))
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=11 * mm,
        bottomMargin=10 * mm,
        title="NyaySaathi Solution Document",
        author="NyaySaathi project",
    )
    document.build(story(summary, kb))
    pages = len(PdfReader(str(OUTPUT)).pages)
    state = "real results" if summary else "RESULTS PENDING (do not submit this version)"
    print(f"Saved {OUTPUT.name}: {pages} pages, {state}")
    if pages > 2:
        print("ERROR: the document is longer than two pages.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
