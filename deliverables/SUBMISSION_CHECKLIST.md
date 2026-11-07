# Final submission checklist

Tick an item only after you have seen it work yourself.

## Before anything goes public

- [ ] `.env.example` has an empty `GEMINI_API_KEY=` line
- [ ] Any key that was exposed has been deleted or replaced, including the old OpenAI key
- [ ] `git status` does not list `.env`
- [ ] `pytest` shows no failures

## Real results

- [ ] `GEMINI_API_KEY` is in `.env`, and `python scripts/check_setup.py --live` shows all `PASS`
- [ ] `python -m evaluation.run_evals` has finished (use `--resume` if a daily limit stopped it)
- [ ] `raw_outputs/evaluation_summary.json` says `"run_type": "REAL"`
- [ ] You have read `raw_outputs/TEST_REPORT.md` and can explain each failure
- [ ] Raw output files have not been edited by hand
- [ ] `evaluation/manual_review_template.md` is filled in by the actual reviewer, or the documents say it was not done

## Deliverables

- [ ] `python scripts/build_solution_pdf.py` was run after the evaluation
- [ ] The PDF is two pages and no longer says RESULTS PENDING
- [ ] Each claim in the PDF matches what you saw
- [ ] The PDF's tools section lists every AI tool you actually used, in your own words
- [ ] Submitted through the placement cell's form before the 48-hour deadline
- [ ] GitHub repository is public and contains no secrets
- [ ] App is deployed on Streamlit Community Cloud, and its link works in a private browser window
- [ ] Voice input was tried with a real microphone, in Hindi and in English
- [ ] Walkthrough recorded in about three minutes, with your real results

## Be ready to explain in the interview

- [ ] Why consumer disputes only
- [ ] Why the app runs on Gemini's free tier, and how to connect a company's model from `.env`
- [ ] Practise: run the app on a new complaint you have not tried before
- [ ] What happens in one chat turn, step by step
- [ ] How an invented section gets caught, and what could still get through
- [ ] What the confidence label does and does not mean
- [ ] What you would do next
