"""The eight pages of NyaySaathi."""

import hashlib
import html

import streamlit as st

from core import case_builder, document_generator, evidence_checker, practice_mode, rights
from core.case_builder import PROVENANCE_LABELS
from core.citation_validator import Confidence
from core.document_generator import DOCUMENT_TYPES
from ui.common import (
    DISCLAIMER,
    confidence_badge,
    get_conversation,
    go_to,
    is_mock_mode,
    knowledge_base,
    need_case,
    note,
    privacy_notice,
    provider,
    run_ai,
    t,
    transcript,
    user_words,
    working_language,
)

CATEGORIES = [
    ("Refund not received", "You returned or cancelled an order, and the money has not come back."),
    ("Defective or damaged product", "What arrived was faulty, broken or not as described."),
    ("Company refusing a refund", "The seller or company says no to a refund or return."),
    ("Cancelled orders and services", "An order or service was cancelled, or you were charged for cancelling."),
    ("Wrong or unauthorised charges", "Repeated deductions, or charges you did not agree to."),
    ("Warranty and replacement disputes", "A warranty or replacement is not being honoured."),
    ("Misleading advertisements", "The product or service was not what the advertisement promised."),
    ("Promised service not provided", "You paid for a service that was poor or never delivered."),
]
BADGE_CLASS = {"user_stated": "user", "ai_inference": "ai", "unverified": "unverified"}


def _cards(items: list[tuple[str, str]]) -> str:
    cards = "".join(
        f'<div class="ns-card"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>'
        for title, text in items
    )
    return f'<div class="ns-grid">{cards}</div>'


# ---------- Home ----------


def home() -> None:
    st.markdown(
        f"""<div class="ns-hero"><h1>NyaySaathi</h1>
        <div class="ns-tag">{html.escape(t("tagline"))}</div>
        <p>{html.escape(t("hero_text"))}</p></div>""",
        unsafe_allow_html=True,
    )
    st.button(t("start"), type="primary", on_click=go_to, args=("nav_chat",))
    st.caption("A simple place to begin when a purchase or service has not gone as expected.")

    st.markdown(f'<div class="ns-section">{html.escape(t("how"))}</div>', unsafe_allow_html=True)
    steps = [
        ("1", "Tell your story", "Type or speak in English, Hindi or Hinglish. We ask questions about anything important that is missing."),
        ("2", "Organise your case", "See your facts, timeline and evidence in one place. You can correct anything."),
        ("3", "Know your options and act", "Read verified legal information, follow a practical plan, and prepare documents to review."),
    ]
    st.markdown(
        '<div class="ns-grid">'
        + "".join(
            f'<div class="ns-card"><div class="ns-step">{n}</div><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>'
            for n, title, text in steps
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(f'<div class="ns-section">{html.escape(t("problems"))}</div>', unsafe_allow_html=True)
    st.markdown(_cards(CATEGORIES), unsafe_allow_html=True)

    st.markdown('<div class="ns-section">Please read this</div>', unsafe_allow_html=True)
    note(DISCLAIMER, "warn")


# ---------- Chat ----------


def _queue_message() -> None:
    draft = st.session_state.chat_draft.strip()
    if draft:
        st.session_state.pending_message = draft
    st.session_state.chat_draft = ""


def _render_turn(turn) -> None:
    st.markdown(turn.display_text)
    if turn.blocked:
        note("An automatic check found legal claims in the draft answer that it could not verify, so they were not shown.", "warn")
    if turn.confidence:
        st.markdown(confidence_badge(turn.confidence), unsafe_allow_html=True)
    for reason in turn.lawyer_reasons:
        note(f"Lawyer recommended: {reason}", "danger")
    if turn.sources:
        with st.expander(f"Sources used ({len(turn.sources)})"):
            for result in turn.sources:
                provision = result.provision
                st.markdown(f"**{provision.heading}** — {provision.label}")
                st.markdown(f"> {provision.quote}")
                st.markdown(f"[Official source]({provision.document.url}) · checked {provision.document.last_verified}")
                if result.not_yet_in_force:
                    st.caption(f"Not in force until {provision.in_force_from.isoformat()}.")


def _voice_input() -> None:
    """Microphone recording. The transcript goes into the text box to review before sending."""
    with st.expander("Speak instead of typing"):
        spoken = st.selectbox("Language you will speak", ["Hindi", "English"], key="voice_language")
        audio = st.audio_input("Record your problem", key="voice_recording")
        st.caption(
            "Your browser will ask for microphone permission. The recording is sent to the AI provider to convert it to text. "
            "If recording does not work on your browser, please type in the box below."
        )
        if audio is None:
            return
        audio_bytes = audio.getvalue()
        digest = hashlib.sha256(audio_bytes).hexdigest()
        if digest == st.session_state.last_audio_hash:
            return
        ai = provider()
        if ai is None:
            return
        language_code = {"Hindi": "hi", "English": "en"}[spoken]
        text = run_ai("Converting your speech to text...", ai.transcribe, audio_bytes, "speech.wav", language_code)
        if text:
            st.session_state.last_audio_hash = digest
            existing = st.session_state.chat_draft.strip()
            st.session_state.chat_draft = f"{existing} {text}".strip()
            st.rerun()


def chat() -> None:
    st.title(t("nav_chat"))
    st.caption("Explain what happened in your own words. You can add details as the conversation goes on.")
    note(privacy_notice(), "info")

    conversation = st.session_state.conversation
    if conversation:
        turns = iter(conversation.turns)
        for message in conversation.messages:
            if message["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(message["content"])
            else:
                with st.chat_message("assistant"):
                    _render_turn(next(turns))

    pending = st.session_state.pending_message
    if pending:
        st.session_state.pending_message = None
        conversation = get_conversation()
        if conversation:
            with st.chat_message("user"):
                st.markdown(pending)
            turn = run_ai("Reading your message and checking verified sources...", conversation.respond, pending)
            if turn is None:
                st.session_state.chat_draft = pending  # Keep their words so they can retry.
            else:
                st.rerun()

    _voice_input()
    st.text_area(
        t("type_here"),
        key="chat_draft",
        height=120,
        placeholder="Example: I ordered a phone online. It was defective, I returned it, and I have not received my refund.",
    )
    send_col, case_col = st.columns([1, 2])
    send_col.button(t("send"), type="primary", on_click=_queue_message, use_container_width=True)
    if conversation and conversation.messages:
        case_col.button("Organise this into my case →", on_click=go_to, args=("nav_case",), use_container_width=True)


# ---------- Case builder ----------


def _provenance_badge(fact: dict) -> str:
    provenance = fact.get("provenance", "unverified")
    return f'<span class="ns-badge {BADGE_CLASS.get(provenance, "unverified")}">{PROVENANCE_LABELS.get(provenance, provenance)}</span>'


def _edit_fact(fact: dict, label: str, key: str) -> None:
    """Show a fact to edit. A changed fact counts as coming from the user."""
    st.markdown(f"**{html.escape(label)}** &nbsp;{_provenance_badge(fact)}", unsafe_allow_html=True)
    new_text = st.text_input(label, value=fact["text"], key=key, label_visibility="collapsed")
    if new_text != fact["text"]:
        fact.update(text=new_text, provenance="user_stated", user_quote=new_text, flagged=False)
        _invalidate_outputs()


def _edit_fact_list(facts: list[dict], label: str, key: str) -> None:
    st.markdown(f"**{label}**")
    for index, fact in enumerate(facts):
        st.markdown(_provenance_badge(fact), unsafe_allow_html=True)
        new_text = st.text_input(f"{label} {index + 1}", value=fact["text"], key=f"{key}_{index}", label_visibility="collapsed")
        if new_text != fact["text"]:
            fact.update(text=new_text, provenance="user_stated", user_quote=new_text, flagged=False)
            _invalidate_outputs()
    added = st.text_input(f"Add to: {label}", key=f"{key}_add", placeholder="Add something here if it is missing")
    if added.strip() and st.session_state.get(f"{key}_added") != added:
        st.session_state[f"{key}_added"] = added
        facts.append({"text": added.strip(), "provenance": "user_stated", "user_quote": added.strip(), "flagged": False})
        _invalidate_outputs()
        st.rerun()


def _edit_lines(items: list[str], label: str, key: str) -> list[str]:
    value = st.text_area(label, value="\n".join(items), key=key, help="One item per line")
    return [line.strip() for line in value.split("\n") if line.strip()]


def _invalidate_outputs() -> None:
    """Results built from the older case are out of date once it changes."""
    for name in ("rights_cards", "action_plan", "evidence", "document"):
        st.session_state[name] = None


def _build_case_now() -> None:
    ai = provider()
    if ai is None:
        return
    case = run_ai("Organising your facts...", case_builder.build_case, ai, transcript(), user_words())
    if case:
        st.session_state.case = case
        st.session_state.case_version += 1
        _invalidate_outputs()
        st.rerun()


def build_case() -> None:
    st.title(t("nav_case"))
    st.write("We turn your story into an organised case. Check it carefully, and correct anything that is wrong.")
    st.caption("Take a moment to review each detail. You can edit the wording before using it in the next steps.")

    conversation = st.session_state.conversation
    has_chat = bool(conversation and conversation.messages)
    if has_chat:
        note(f"Using your chat so far ({sum(m['role'] == 'user' for m in conversation.messages)} of your messages).", "info")
    else:
        # Streamlit forgets a widget's value when its page is closed, so the story is kept separately.
        st.session_state.manual_story = st.text_area(
            "Tell your story here, or use the AI Legal Chat first",
            value=st.session_state.manual_story,
            height=130,
            placeholder="What did you buy, from whom, when, for how much, what went wrong, and what do you want?",
        )
        note(privacy_notice(), "info")

    if st.button("Update my case" if st.session_state.case else "Build my case", type="primary"):
        if not (has_chat or st.session_state.manual_story.strip()):
            st.warning("Please tell us about your problem first.")
        else:
            _build_case_now()

    case = st.session_state.case
    if not case:
        return

    version = st.session_state.case_version
    st.divider()
    st.markdown(
        "**How to read the labels:** "
        + " ".join(f'<span class="ns-badge {BADGE_CLASS[k]}">{label}</span>' for k, label in PROVENANCE_LABELS.items()),
        unsafe_allow_html=True,
    )
    for warning in case.get("warnings", []):
        note(warning, "warn")

    case["title"] = st.text_input("Case title", value=case["title"], key=f"title_{version}")
    case["nature_of_dispute"] = st.text_area("Nature of dispute", value=case["nature_of_dispute"], key=f"nature_{version}")

    st.divider()
    st.markdown("#### Parties involved")
    _edit_fact(case["consumer"], "You, the consumer", f"consumer_{version}")
    _edit_fact_list(case["opposite_parties"], "Company or seller", f"parties_{version}")
    _edit_fact(case["amount_involved"], "Amount involved", f"amount_{version}")

    st.divider()
    st.markdown("#### Timeline of events")
    for index, entry in enumerate(case["timeline"]):
        date_col, event_col = st.columns([1, 3])
        new_date = date_col.text_input(f"Date {index + 1}", value=entry["date_text"], key=f"date_{version}_{index}")
        if new_date != entry["date_text"]:
            entry["date_text"] = new_date
            entry["event"].update(provenance="user_stated", flagged=False)
            _invalidate_outputs()
        with event_col:
            _edit_fact(entry["event"], f"Event {index + 1}", f"event_{version}_{index}")

    st.divider()
    st.markdown("#### What was promised and what happened")
    _edit_fact_list(case["company_promised"], "What the company promised", f"promised_{version}")
    _edit_fact_list(case["what_happened"], "What actually happened", f"happened_{version}")
    st.divider()
    st.markdown("#### Supporting information")
    _edit_fact_list(case["evidence_available"], "Evidence you have", f"have_{version}")
    case["evidence_required"] = _edit_lines(case["evidence_required"], "Evidence still required", f"required_{version}")
    case["missing_information"] = _edit_lines(case["missing_information"], "Important missing information", f"missing_{version}")
    _edit_fact(case["desired_resolution"], "What you want", f"desired_{version}")

    st.download_button(
        "Download case summary (TXT)",
        case_builder.case_to_text(case).encode("utf-8"),
        file_name="nyaysaathi_case_summary.txt",
    )
    st.button("Next: Know My Rights →", on_click=go_to, args=("nav_rights",), type="primary")


# ---------- Rights and next steps ----------


def _law_card(card: rights.RightsCard) -> str:
    provision = card.provision
    return f"""<div class="ns-law">
    <h4>{html.escape(provision.heading)}</h4>
    <div class="ns-ref">{html.escape(provision.label)}</div>
    {confidence_badge(card.confidence)}
    <blockquote>{html.escape(provision.quote)}</blockquote>
    <div class="ns-label">What this means in simple language</div><p>{html.escape(provision.plain_language)}</p>
    <div class="ns-label">How it may relate to your case</div><p>{html.escape(card.how_it_may_relate)}</p>
    <div class="ns-label">Verification status</div><p>{html.escape(card.verification_status)}</p>
    <a href="{html.escape(provision.document.url)}" target="_blank" rel="noopener">Read the official source ↗</a>
    </div>"""


def know_rights() -> None:
    st.title(t("nav_rights"))
    st.caption("Review the provisions and practical options that may be relevant to the facts in your case.")
    if not need_case():
        return
    note(
        "The badge shows how well a statement is backed by a verified source. It is not your chance of winning.",
        "info",
    )
    case_text = case_builder.case_to_text(st.session_state.case)

    if st.button("Find my rights and next steps", type="primary"):
        ai = provider()
        if ai:
            kb = knowledge_base()
            st.session_state.rights_cards = run_ai(
                "Checking verified sources...", rights.build_rights_cards, ai, kb, case_text, working_language()
            )
            st.session_state.action_plan = run_ai(
                "Preparing your action plan...", rights.build_action_plan, ai, kb, case_text, working_language()
            )

    cards = st.session_state.rights_cards
    if cards is not None:
        st.markdown('<div class="ns-section">Your legal information</div>', unsafe_allow_html=True)
        if not cards:
            badge = confidence_badge(Confidence.INSUFFICIENT)
            st.markdown(badge, unsafe_allow_html=True)
            note("I could not verify the exact legal provision. Please consult a qualified lawyer or check the official government source.", "warn")
        for card in cards:
            st.markdown(_law_card(card), unsafe_allow_html=True)

    plan = st.session_state.action_plan
    if plan:
        st.markdown('<div class="ns-section">Recommended next steps</div>', unsafe_allow_html=True)
        for number, step in enumerate(plan["steps"], start=1):
            st.markdown(f"**Step {number}: {step['title']}**")
            st.markdown(step["detail"])
        if plan["removed_sentences"]:
            note(plan["unverified_notice"], "warn")
        note(plan["no_guarantee_notice"], "warn")
        st.button("Next: Generate Documents →", on_click=go_to, args=("nav_docs",))


# ---------- Documents ----------


def documents() -> None:
    st.title(t("nav_docs"))
    st.caption("Prepare a draft based on your case details. Read it carefully and fill in any missing information.")
    if not need_case():
        return
    note(document_generator.NOT_SENT_NOTICE, "info")
    choice = st.selectbox("Which document do you need?", list(DOCUMENT_TYPES), format_func=DOCUMENT_TYPES.get)
    extra = st.text_area(
        "Anything to add? (optional)",
        placeholder="Example: the company replied that the return window has closed.",
        key="document_note",
    )
    if st.button("Generate draft", type="primary"):
        ai = provider()
        if ai:
            document = run_ai(
                "Drafting your document...",
                document_generator.generate_document,
                ai,
                knowledge_base(),
                choice,
                case_builder.case_to_text(st.session_state.case),
                user_words(),
                extra,
            )
            if document:
                st.session_state.document = document
                st.session_state.document_text = document.text
                st.session_state.document_version += 1

    document = st.session_state.document
    if not document:
        return
    st.markdown(f'<div class="ns-note danger"><b>{document_generator.DRAFT_WARNING}</b></div>', unsafe_allow_html=True)
    for warning in document.warnings:
        note(warning, "warn")
    st.caption("Replace everything in [SQUARE BRACKETS] with your details. You can edit any part below.")
    # Edits are kept separately, because Streamlit forgets a widget's value when its page is closed.
    text = st.text_area(
        "Your document",
        value=st.session_state.document_text,
        key=f"document_editor_{st.session_state.document_version}",
        height=520,
    )
    st.session_state.document_text = text

    txt_col, docx_col = st.columns(2)
    txt_col.download_button(
        "Download TXT", document_generator.to_txt(text), file_name=f"{document.document_type}.txt", use_container_width=True
    )
    docx_col.download_button(
        "Download DOCX",
        document_generator.to_docx(text),
        file_name=f"{document.document_type}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    with st.expander("Copy the document"):
        st.caption("Use the copy icon at the top right of this box.")
        st.code(text, language=None, wrap_lines=True)


# ---------- Evidence ----------


def evidence() -> None:
    st.title(t("nav_evidence"))
    st.caption("Use this list to keep track of documents that may support your complaint.")
    if not need_case():
        return
    st.write("These are the documents that could support your case, and why each one matters.")
    if st.button("Create my checklist", type="primary"):
        ai = provider()
        if ai:
            st.session_state.evidence = run_ai(
                "Creating your checklist...",
                evidence_checker.build_checklist,
                ai,
                case_builder.case_to_text(st.session_state.case),
                user_words(),
                working_language(),
            )

    items = st.session_state.evidence
    if not items:
        return
    for index, item in enumerate(items):
        mentioned = item["status"] == evidence_checker.USER_MENTIONED
        st.checkbox(f"**{item['item']}**", value=mentioned, key=f"evidence_{index}")
        st.caption(item["why_it_matters"])
        if mentioned:
            st.caption(f'You mentioned this: "{item["user_quote"]}"')
    note("Ticks are for your own tracking. NyaySaathi has not seen or checked these documents.", "info")


# ---------- Practice ----------


def practice() -> None:
    st.title(t("nav_practice"))
    st.caption("Rehearse how you might explain the issue before speaking with a company representative.")
    st.markdown(f'<div class="ns-note danger"><b>{practice_mode.PRACTICE_LABEL}</b></div>', unsafe_allow_html=True)

    session = st.session_state.practice
    if session is None:
        st.write("Practise explaining your complaint to a simulated company representative, then get feedback.")
        role = st.selectbox("Who do you want to practise with?", list(practice_mode.ROLES), format_func=lambda r: practice_mode.ROLES[r].capitalize())
        if st.button("Start practice", type="primary"):
            ai = provider()
            if ai:
                case = st.session_state.case
                summary = case_builder.case_to_text(case) if case else ""
                st.session_state.practice = practice_mode.PracticeSession(ai, summary, role, working_language())
                st.session_state.practice_feedback = None
                st.rerun()
        return

    for message in session.messages:
        with st.chat_message("user" if message["role"] == "user" else "assistant"):
            st.markdown(message["content"])

    said = st.chat_input("Explain your complaint...")
    if said:
        reply = run_ai("The representative is replying...", session.say, said)
        if reply is not None:
            st.rerun()

    end_col, reset_col = st.columns(2)
    if session.messages and end_col.button("End practice and get feedback", type="primary", use_container_width=True):
        st.session_state.practice_feedback = run_ai("Reviewing your practice...", session.feedback)
    if reset_col.button("Start over", use_container_width=True):
        st.session_state.practice = None
        st.session_state.practice_feedback = None
        st.rerun()

    feedback = st.session_state.practice_feedback
    if feedback:
        st.markdown('<div class="ns-section">Your feedback</div>', unsafe_allow_html=True)
        st.markdown(f"**Clarity:** {feedback['clarity']}")
        st.markdown(f"**Evidence presented:** {feedback['evidence_presented']}")
        st.markdown(f"**Strength of your explanation:** {feedback['strength_of_explanation']}")
        st.markdown("**Missing facts:**")
        st.markdown("\n".join(f"- {item}" for item in feedback["missing_facts"]) or "- None noted")
        st.markdown("**Questions to prepare for:**")
        st.markdown("\n".join(f"- {item}" for item in feedback["questions_to_prepare_for"]) or "- None noted")


# ---------- About ----------


def about() -> None:
    st.title(t("nav_about"))
    st.caption("A little more about what NyaySaathi does, how it handles information, and where its limits are.")
    note(DISCLAIMER, "warn")

    st.markdown("#### What NyaySaathi covers")
    st.write(
        "Consumer disputes and refund complaints in India only. For anything else, or for complex, urgent, "
        "high-value or possibly criminal matters, it refers you to a qualified lawyer."
    )
    st.markdown("#### How it tries to avoid invented law")
    st.markdown(
        "- It may cite only provisions in a small knowledge base of official documents.\n"
        "- A script checks the wording of those provisions against the official documents.\n"
        "- Before you see an answer, code checks each citation. Answers with unsupported legal claims are corrected or blocked.\n"
        "- It does not cite court judgments in this version."
    )
    st.markdown("#### Your privacy")
    st.write(privacy_notice())
    st.write("Use **Delete my conversation** in the sidebar at any time to clear this session.")

    st.markdown("#### Known limits")
    st.markdown(
        "- No qualified lawyer has reviewed the knowledge base or the answers.\n"
        "- The knowledge base is a selection of provisions, not all of consumer law, and it can go out of date.\n"
        "- Automatic checks catch specific patterns. They cannot prove that an explanation is correct.\n"
        "- Documents are drafts. NyaySaathi never sends or files anything.\n"
        "- It does not read uploaded documents in this version."
    )

    st.markdown("#### Official sources used")
    kb = knowledge_base()
    for document in kb.documents.values():
        st.markdown(f"- [{document.title}]({document.url}) — checked {document.last_verified}")
    if is_mock_mode():
        note("This app is running in MOCK mode. Answers are scripted and do not come from AI.", "danger")


PAGES = {
    "nav_home": home,
    "nav_chat": chat,
    "nav_case": build_case,
    "nav_rights": know_rights,
    "nav_docs": documents,
    "nav_evidence": evidence,
    "nav_practice": practice,
    "nav_about": about,
}
