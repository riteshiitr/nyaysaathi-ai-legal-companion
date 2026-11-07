"""Visual styling for NyaySaathi: a typeset legal document rather than a dashboard.

.streamlit/config.toml sets the palette, radius and fonts for Streamlit's own widgets.
This file only covers what that theme cannot reach. Selectors were checked against the
rendered page on Streamlit 1.67, so recheck them after upgrading Streamlit.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Noto+Serif+Devanagari:wght@400;600&family=Noto+Sans+Devanagari:wght@400;600&display=swap');

:root {
    --gold: #A67C52;
    --gold-hover: #896442;
    --gold-ink: #7A5A38;
    --gold-light: #C9A67E;
    --gold-soft: #EFE3D2;

    --ivory: #F3EBDD;
    --sandstone: #E5DDCE;
    --card: #FBF9F4;
    --line: #D8CEBD;

    --ink: #292D26;
    --ink-on-gold: #171A14;
    --muted: #716D63;
    --muted-on-ivory: #5F5B52;

    --forest: #34483A;
    --forest-light: #465C4B;

    --green: #2F4E36;
    --green-soft: #E3E9DC;
    --amber: #6A4A20;
    --amber-rule: #9A6A2F;
    --amber-soft: #F3E6CF;
    --red: #7D3D33;
    --red-rule: #934B40;
    --red-soft: #F3E3DC;

    --serif: 'Source Serif 4', 'Noto Serif Devanagari', serif;
}

/* ---------- Page and type ---------- */

.block-container {
    max-width: 880px;
    padding-top: 3rem;
    padding-bottom: 4rem;
}

[data-testid="stMain"] h1 {
    color: var(--forest);
    font-size: 2.35rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}

[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4 {
    color: var(--forest);
    font-weight: 600;
}

[data-testid="stMain"] h4 {
    font-size: 1.15rem;
}

/* Streamlit fades captions and quotes with opacity, which a colour alone cannot undo. */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: var(--muted-on-ivory);
    opacity: 1;
}

[data-testid="stMain"] [data-testid="stMarkdownContainer"] a {
    text-decoration-color: var(--gold-light);
    text-underline-offset: 2px;
}

[data-testid="stMain"] [data-testid="stMarkdownContainer"] a:hover {
    color: var(--gold-hover);
    text-decoration-color: currentColor;
}

/* Official wording is set in serif, so it reads differently from AI-written text. */
[data-testid="stMarkdownContainer"] blockquote,
.ns-law blockquote {
    margin: 0.7rem 0;
    padding: 0.15rem 0 0.15rem 1rem;
    border-left: 2px solid var(--gold);
    color: var(--ink);
    opacity: 1;
    font-family: var(--serif);
    font-size: 0.97rem;
    line-height: 1.6;
}

[data-testid="stMarkdownContainer"] blockquote p {
    color: inherit;
    font-size: inherit;
}

[data-testid="stSkipToContent"] {
    color: var(--forest);
    background: var(--card);
}

hr {
    border-color: var(--line);
}

#MainMenu,
footer {
    visibility: hidden;
}

/* ---------- Sidebar ---------- */

.ns-brand {
    font-family: var(--serif);
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--ivory);
    margin: 0;
    line-height: 1.2;
}

.ns-brand-sub {
    font-size: 0.85rem;
    color: #D8D0BF;
    margin: 0.2rem 0 1.25rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--gold-light);
}

/* The page menu is a radio group: hide the circles and mark the open page with a gold rule. */
/* Each wrapper shrinks to its text by default, so the highlight would not fill the row. */
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
section[data-testid="stSidebar"] [data-testid="stRadio"],
section[data-testid="stSidebar"] [data-testid="stRadioGroup"] {
    width: 100%;
}

section[data-testid="stSidebar"] [data-testid="stRadioGroup"] {
    align-items: stretch;
    gap: 0;
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"] {
    width: 100%;
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-left: 2px solid transparent;
    cursor: pointer;
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {
    display: none;
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {
    background-color: var(--forest-light);
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
    border-left-color: var(--gold-light);
    background-color: var(--forest-light);
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {
    font-weight: 600;
    color: #FFFFFF;
}

section[data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:focus-visible) {
    outline: 2px solid var(--gold-light);
    outline-offset: -2px;
}

section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #D8D0BF;
}

/* ---------- Buttons ---------- */

button[data-testid="stBaseButton-primary"] {
    background-color: var(--gold);
    border: 1px solid var(--gold);
    color: var(--ink-on-gold);
    box-shadow: none;
}

button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primary"]:active {
    background-color: var(--gold-hover);
    border-color: var(--gold-hover);
    color: var(--card);
}

button[data-testid="stBaseButton-primary"]:focus:not(:hover):not(:active) {
    background-color: var(--gold);
    color: var(--ink-on-gold);
}

/* Streamlit colours the label's inner paragraph separately. */
button[data-testid="stBaseButton-primary"] p,
button[data-testid="stBaseButton-secondary"] p {
    color: inherit;
    font-weight: 600;
}

button[data-testid="stBaseButton-secondary"] {
    background-color: var(--card);
    border: 1px solid var(--line);
    color: var(--ink);
}

button[data-testid="stBaseButton-secondary"]:hover {
    background-color: var(--sandstone);
    border-color: var(--gold);
    color: var(--ink);
}

button[data-testid="stBaseButton-primary"]:focus-visible,
button[data-testid="stBaseButton-secondary"]:focus-visible {
    outline: 2px solid var(--forest);
    outline-offset: 2px;
    box-shadow: none;
}

section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
    background-color: transparent;
    border-color: #718071;
    color: var(--ivory);
}

section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
    background-color: var(--forest-light);
    border-color: var(--gold-light);
    color: #FFFFFF;
}

button[data-testid="stChatInputSubmitButton"]:not(:disabled) {
    background-color: var(--gold);
    color: var(--ink-on-gold);
}

/* ---------- Inputs ---------- */

/* The theme already gives these widgets a gold focus border. It only needs the lighter fill. */
[data-testid="stMain"] [data-testid="stTextInputRootElement"],
[data-testid="stMain"] [data-testid="stTextAreaRootElement"],
[data-testid="stMain"] [data-testid="stSelectbox"] [role="group"],
[data-testid="stMain"] [data-testid="stAudioInput"] > div,
[data-testid="stChatInput"] > div {
    background-color: var(--card);
}

/* The recording timer otherwise keeps the code-block background. */
[data-testid="stAudioInput"] [data-testid="stAudioInputWaveformTimeCode"] {
    background-color: transparent;
}

[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder {
    color: var(--muted);
    opacity: 1;
}

[data-testid="stExpander"] details {
    background-color: var(--card);
    border-color: var(--line);
}

[data-testid="stExpander"] summary:hover {
    color: var(--gold-ink);
}

/* ---------- Chat ---------- */

[data-testid="stChatMessage"] {
    padding: 1rem 1.15rem;
    margin-bottom: 0.75rem;
    background-color: var(--card);
    border: 1px solid var(--line);
    border-radius: 3px;
}

/* The user's words sit on sandstone, and the assistant's on the lighter card. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background-color: var(--sandstone);
    border-color: var(--sandstone);
}

[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    border-radius: 3px;
}

[data-testid="stChatMessageAvatarUser"] {
    background-color: var(--gold);
    color: var(--ink-on-gold);
}

[data-testid="stChatMessageAvatarAssistant"] {
    background-color: var(--forest);
    color: var(--ivory);
}

[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
    line-height: 1.65;
}

[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3,
[data-testid="stChatMessage"] h4 {
    font-size: 1.12rem;
    padding: 1rem 0 0.35rem;
}

[data-testid="stChatMessage"] hr {
    margin: 0.75rem 0;
}

/* ---------- Home ---------- */

.ns-hero {
    padding: 0.5rem 0 1.5rem;
}

[data-testid="stMain"] .ns-hero h1 {
    margin: 0 0 0.35rem;
    padding: 0;
    font-size: 3.1rem;
    line-height: 1.1;
}

.ns-hero .ns-tag {
    color: var(--gold-ink);
    font-family: var(--serif);
    font-size: 1.15rem;
    font-style: italic;
    margin-bottom: 1rem;
}

.ns-hero p {
    max-width: 640px;
    margin: 0;
    font-size: 1.1rem;
    line-height: 1.65;
}

.ns-section {
    margin: 2.5rem 0 0.75rem;
    color: var(--forest);
    font-family: var(--serif);
    font-size: 1.35rem;
    font-weight: 600;
}

.ns-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 2rem;
}

.ns-grid:has(.ns-step) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
}

.ns-card {
    padding: 0.8rem 0 1rem;
    border-top: 1px solid var(--line);
}

[data-testid="stMain"] .ns-card h4 {
    margin: 0 0 0.2rem;
    padding: 0;
    font-size: 1.05rem;
}

.ns-card p {
    margin: 0;
    color: var(--muted-on-ivory);
    font-size: 0.93rem;
    line-height: 1.55;
}

.ns-step {
    color: var(--gold-ink);
    font-family: var(--serif);
    font-size: 1.6rem;
    line-height: 1.3;
}

/* ---------- Notices ---------- */

.ns-note {
    margin: 0.7rem 0;
    padding: 0.7rem 0.95rem;
    border-left: 3px solid var(--line);
    background-color: var(--card);
    font-size: 0.93rem;
    line-height: 1.55;
}

.ns-note.info {
    border-left-color: var(--forest-light);
    background-color: var(--sandstone);
    color: var(--forest);
}

.ns-note.warn {
    border-left-color: var(--amber-rule);
    background-color: var(--amber-soft);
    color: var(--amber);
}

.ns-note.danger {
    border-left-color: var(--red-rule);
    background-color: var(--red-soft);
    color: var(--red);
}

.ns-mock {
    margin-bottom: 1rem;
    padding: 0.55rem 0.95rem;
    border-left: 3px solid var(--red-rule);
    background-color: var(--red-soft);
    color: var(--red);
    font-size: 0.9rem;
    font-weight: 600;
}

/* ---------- Status badges ---------- */

.ns-badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border: 1px solid transparent;
    border-radius: 2px;
    font-size: 0.76rem;
    font-weight: 600;
    white-space: nowrap;
}

.ns-badge.supported { background-color: var(--green-soft); border-color: #BFCDB9; color: var(--green); }
.ns-badge.partial { background-color: var(--amber-soft); border-color: #DDC59C; color: var(--amber); }
.ns-badge.insufficient { background-color: var(--red-soft); border-color: #DDBDB1; color: var(--red); }
.ns-badge.user { background-color: var(--gold-soft); border-color: #D8C2A6; color: #684C2F; }
.ns-badge.unverified { background-color: var(--amber-soft); border-color: #DDC59C; color: var(--amber); }
/* A dashed edge marks the model's own inference, so the label does not rely on colour alone. */
.ns-badge.ai { background-color: var(--sandstone); border: 1px dashed var(--forest-light); color: var(--forest); }

/* ---------- Legal information cards ---------- */

.ns-law {
    margin-bottom: 1rem;
    padding: 1.2rem 1.35rem;
    background-color: var(--card);
    border: 1px solid var(--line);
    border-radius: 3px;
}

[data-testid="stMain"] .ns-law h4 {
    margin: 0;
    padding: 0;
    font-size: 1.15rem;
}

.ns-law .ns-ref {
    margin: 0.2rem 0 0.6rem;
    color: var(--muted);
    font-size: 0.87rem;
}

.ns-law .ns-label {
    margin-top: 0.9rem;
    color: var(--forest);
    font-size: 0.88rem;
    font-weight: 600;
}

.ns-law p {
    margin: 0.1rem 0;
    font-size: 0.97rem;
    line-height: 1.6;
}

.ns-law a {
    display: inline-block;
    margin-top: 0.8rem;
    font-size: 0.92rem;
    font-weight: 600;
}

/* ---------- Mobile ---------- */

@media (max-width: 640px) {
    .block-container {
        padding: 2.5rem 1rem 3rem;
    }

    [data-testid="stMain"] .ns-hero h1 {
        font-size: 2.3rem;
    }

    .ns-grid,
    .ns-grid:has(.ns-step) {
        grid-template-columns: minmax(0, 1fr);
    }

    .ns-law {
        padding: 1rem;
    }
}
</style>
"""
