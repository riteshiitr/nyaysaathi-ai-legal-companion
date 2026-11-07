# Raw outputs

This folder holds the original, unedited output of each test case, written by
`python -m evaluation.run_evals`.

**Check the status in `evaluation_summary.json`.** If that file is not in this
folder, the real evaluation has not been run yet.

## Rules

- Files here must come from real model runs. Do not edit them by hand.
- `mock/` holds scripted runs, each labelled `"run_type": "MOCK"`. They only show
  that the framework works, and must not be submitted as real AI results.
- Test cases use synthetic data only. Never put a real person's details here.

## What each file records

The input test case, every AI request and original response, the retrieved sources,
the model identifier, execution timestamps, token usage, execution status, the
pipeline's output and its automatic scores.
