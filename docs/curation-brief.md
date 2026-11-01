# Task curation brief (for Ethan)

72 fresh-task candidates from the 76 held-out trajectories. 4 excluded
(continuation "Feedback for the next attempt:" prompts — the DAPT family's
real task is the verifier itself; keep DAPT out of v1 or hand-build it).

## What I need from you

Pick **10–20**. Bias toward:
- **Families with train-side memory mass** (MCP 16, conventions 6): the memory
  actually has family rules for these — that's where lift is measurable.
- **Diversity of dependency tag** — we want task, user, AND environment
  represented so results decompose meaningfully.
- **Verifiability** — tasks whose expected output is a file/JSON/number beat
  tasks graded by a human eye.

## Already spotted (from the sample)

- **t0125 / t0288 are the same Magnolia Gardens task** (duplicate family
  members in held-out) — pick one.
- **t0192 / t0193 are the same ECS issue** — pick one.
- **t0081/t0096/t0590/t0602 DAPT "Feedback" prompts excluded** — but the DAPT
  family is our single richest memory section (6 rules + known-failures); if
  you want it in, we hand-build its task from the verifier spec.
- **t0251 (WACC calc), t0019 (churn seat analysis), t0339 (M&A model error
  hunt)** — these are spreadsheet-analysis tasks where the memory's MCP
  workplace rules (tab_index API, answers-in-chat, rounding) plausibly lift.

## Format of a curated task (what I'll build from your picks)

For each: {trajId, task prompt, expected-output spec (verifier), dependency
tags, family}. I'll generate the expected-output spec from the trajectory's
verifier result and final artifacts, and you sanity-check that it's neither
ambiguous nor memory-independent.
