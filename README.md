# NyaySaathi: Your AI Legal Companion

*Understand Your Rights. Know Your Options. Take Action.*

NyaySaathi helps ordinary people in India with consumer disputes and refund
complaints. It asks about the problem, organises the facts, explains options using
verified official sources, and prepares draft documents for the user to review.

> NyaySaathi is not a lawyer and does not represent anyone. It provides legal
> information, not legal advice, and its answers can be wrong. No qualified lawyer
> has reviewed its knowledge base.

## Features

| Feature | What it does |
| --- | --- |
| AI Legal Chat | Text or voice in English, Hindi or Hinglish, with follow-up questions before any legal explanation |
| Build My Case | Editable case file that labels each fact as provided by you, AI inference or not verified |
| Know My Rights | Legal information cards with official links and verification status, plus an action plan |
| Generate Documents | Five draft types, downloadable as TXT or DOCX, always marked as drafts, never sent automatically |
| Evidence Checklist | Case-specific items and why each matters, without claiming evidence you did not mention |
| Practice My Argument | Labelled role-play with a simulated company representative, followed by feedback |

## How it works

```text
User message
  → safety rules and AI triage (scope, stage, lawyer flags)
  → search of verified legal provisions (local BM25)
  → AI answer, with a source tag on each legal claim
  → code checks every citation → one corrected retry → otherwise blocked
  → answer, shown with its sources and a confidence label
```

The confidence label describes how well a statement is sourced. It is not a chance
of winning.

| Path | Purpose |
| --- | --- |
| `app.py`, `ui/` | Web interface |
| `config.py` | Settings and the API key |
| `core/ai_engine.py` | The only code that talks to an AI service |
| `core/mock_provider.py` | Scripted stand-in for testing, always labelled MOCK |
| `core/prompts.py` | All AI instructions and output formats |
| `core/conversation.py` | The steps of one chat turn |
| `core/legal_retrieval.py` | Search over the knowledge base |
| `core/citation_validator.py` | Rejects unsupported legal claims |
| `core/safety_guardrails.py` | Rule-based lawyer referrals |
| `core/case_builder.py` | Case file and checks for invented facts |
| `core/rights.py` | Rights cards and action plan |
| `core/evidence_checker.py` | Evidence checklist |
| `core/document_generator.py` | Draft documents and downloads |
| `core/practice_mode.py` | Practice role-play and feedback |
| `knowledge_base/` | Verified legal sources |
| `data/test_cases.json` | 12 synthetic test cases |
| `evaluation/` | Runs and scores the test cases |
| `raw_outputs/` | Unedited test outputs |
| `scripts/` | Setup check, source verification and PDF builder |
| `tests/` | Automated code tests |
| `deliverables/` | Solution document, walkthrough script and submission checklist |

## Install and run on your computer

These commands are for macOS. Run them in the VS Code terminal, inside this project
folder. Python 3.11 or newer is required.

```bash
# 1. Create a private Python environment for this project (only once)
python3 -m venv .venv

# 2. Switch to it (each time you open a new terminal)
source .venv/bin/activate

# 3. Install the packages (only once)
pip install -r requirements-dev.txt

# 4. Create your private settings file (only once)
cp .env.example .env

# 5. Add your key to .env (see below), then check the setup
python scripts/check_setup.py --live

# 6. Start the app, which opens in your browser. Press Ctrl+C to stop it.
streamlit run app.py
```

## Configure the API key

The app uses Google Gemini's free tier by default, so it costs nothing to run.

1. Create a free key at <https://aistudio.google.com/apikey>.
2. In **`.env`** (not `.env.example`), add the line `GEMINI_API_KEY=` followed by your key, and save.
3. Run `python scripts/check_setup.py --live`. All lines should say `PASS`.

Never put your key in `.env.example`, a chat, a screenshot, source code or GitHub.
If that happens, delete the key on the same page and create a new one.

Google may use what is sent on the free tier to improve its products, so use only
synthetic details. The app's privacy notice says this too.

## Swap the AI model

Only `.env` changes. Restart the app afterwards.

```bash
# OpenAI (needs credit on the account)
NYAYSAATHI_PROVIDER=openai
OPENAI_API_KEY=your-key

# Any other service with an OpenAI-style API, such as one a company provides
NYAYSAATHI_PROVIDER=compatible
NYAYSAATHI_API_KEY=your-key
NYAYSAATHI_BASE_URL=https://the-service-address/v1
NYAYSAATHI_MODEL=the-model-name

# A different Gemini model
NYAYSAATHI_MODEL=the-model-name
```

Then run `python scripts/check_setup.py --live`. It sends a plain message and a strict
structured request, because the app needs both to work. A service that does not support
strict JSON schemas will fail this check.

To run the app on a new complaint, start it and type the complaint into AI Legal Chat.

To see the screens without AI or credit, run this. Every screen is labelled MOCK:

```bash
NYAYSAATHI_PROVIDER=mock streamlit run app.py
```

## Run the tests

```bash
# Automated code tests. These use no AI and cost nothing.
pytest

# Downloads the official documents and checks every legal quote against them.
python scripts/verify_sources.py

# The evaluation suite: at least 74 AI calls, with a 7-second wait before each on Gemini.
python -m evaluation.run_evals

# If a free daily limit stops it, run this the next day. It keeps the finished tests.
python -m evaluation.run_evals --resume

# After the evaluation, rebuild the two-page PDF with the real results.
python scripts/build_solution_pdf.py
```

## Where raw outputs are stored

Real results go in `raw_outputs/`, one JSON file per test plus
`evaluation_summary.json` and `TEST_REPORT.md`. Scripted results go separately in
`raw_outputs/mock/` and are labelled MOCK. Never submit those as real results.

## Deploy to Streamlit Community Cloud

1. Rebuild the PDF after a real evaluation, and make sure `pytest` passes.
2. Put the project on GitHub. **First check** that `git status` does not list `.env`.
3. Sign in at <https://share.streamlit.io> with GitHub and choose **Create app**.
4. Select your repository and branch, and set the main file to `app.py`.
5. Under **Advanced settings**, paste the contents of `.streamlit/secrets.toml.example`
   into **Secrets**, with your real key. Python 3.13 is the version tested.
6. Deploy, then test a chat and a voice recording on the public link.

Anyone with the link uses your key's free allowance, and what they type goes to Google.
Turn the app off when it is not needed.

## Known limitations

- No qualified lawyer has reviewed the knowledge base or the answers.
- The citation checker matches patterns. A wrong explanation in plain words, with a
  real citation attached, can still pass.
- The knowledge base is a selection of provisions. It omits RBI refund timelines and
  the RBI Ombudsman, and later changes in the law are not detected automatically.
- Keyword search can miss paraphrases, and a long out-of-scope story can still match
  consumer provisions. Scope depends on the triage step and safety rules.
- Language checks confirm only the script, so Hindi and Hinglish quality needs a human.
  Documents are drafted in English by default.
- It does not read uploaded documents or save cases between sessions.
- Voice input depends on browser microphone permission and on the AI service's audio support.
- User messages are sent to the configured AI service to generate answers.
- Free-tier rate limits can interrupt a session. The app then asks the user to wait and retry.
