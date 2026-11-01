# Verifier spec report: 18 remaining curated tasks (2026-11-01)

Overnight batch. Specs live in `tasks/<trajId>-<slug>.json`, matching the
`t0505-word2vec.json` format exactly (same keys). Every fact in a spec comes
from the trajectory file in the v1.1 corpus or the train-only memory state
(`/tmp/train-only`); nothing was invented. Where a check could not be run
locally, the spec says so in `verifier.checks[i].locallyVerified` /
`localVerification` instead of faking a result.

## Summary

| Task | Spec | Verifier type | Both-ways status | Concerns |
|---|---|---|---|---|
| t0072 | written | chat-message-check | verified both ways (check logic) | needs world MCP container for sources |
| t0124 | written, flagged | chat-message-check | container-required | **FAIL traj, no verifier feedback: expected value unknown — replacement candidate** |
| t0339 | written, flagged | chat-message-check | container-required | **FAIL traj, no verifier feedback: expected value unknown — replacement candidate** |
| t0544 | written | workbook-cell-check | container-required (values pinned from PASS ops) | container eval only |
| t0553 | written | workbook-cell-check | container-required (formulas/values pinned from PASS ops) | container eval only |
| t0125 | written | chat-message-check | verified both ways (check logic) | container for sources |
| t0596 | written | chat-message-check | verified both ways (check logic) | container for sources |
| t0192 | written | repo-hidden-tests | container-required | hidden tests live in the task container |
| t0397 | written, flagged | agent-policy-behavioral | container-required | **FAIL traj, no feedback: graded criterion unknown — replacement candidate** |
| t0720 | written, flagged | agent-policy-behavioral | container-required | **FAIL traj, no feedback; longest trajectory (414 steps) — replacement candidate** |
| t0195 | written | agent-policy-state-check | container-required (state values pinned from PASS run) | container state readback only |
| t0007 | written | repo-hidden-tests | container-required | fixture + expected findings pinned from PASS run |
| t0157 | written, flagged | repo-hidden-tests | container-required | **FAIL traj, no feedback after clean self-tests — replacement candidate** |
| t0443 | written | repo-hidden-tests | container-required | contract fully prompt-pinned |
| t0414 | written | repo-hidden-tests | container-required | contract fully prompt-pinned |
| t0174 | written | algotune-speedup-check | harness mechanics verified locally; rebuild in container | speedup threshold lives in the container grader |
| t0251 | written | chat-message-check | verified both ways (check logic) | container for workbook figures |
| t0019 | written | chat-message-check | verified both ways (check logic) | container for workbooks |

## What was verified locally

- **Chat-value tasks (t0072, t0596, t0125, t0251, t0019):** the check logic was
  executed against the recorded PASS reply (passes) and against a
  hand-constructed wrong variant (2-dp instead of 4-dp values, wrong rounding,
  "compliant" answer that assumes the unavailable attachment, 8.21% gross-debt
  WACC, 1-dp format string) — each is rejected. The wrong variants are check
  discriminators, not simulated agent runs.
- **t0174:** the prompt's benchmark harness was extracted verbatim and run
  against stock pandas: it executes, and the prompt's own equivalence check
  passes. The recorded FAIL (`ModuleNotFoundError: No module named 'pandas'`)
  pins the decisive environment check; the reinstall requirement is a train
  memory item (`/workspace/pandas-dev__pandas`, `.venv`, reinstall after
  editing). A full source build stays in the container.
- **t0544 / t0553:** cell coordinates, values, and formulas pinned verbatim
  from the PASS runs' recorded `set_cell` operations; cross-checked against the
  final messages. Container readback still required.

## Provenance lint

Re-run over all 20 spec files plus the train-only memory (10,909 claims; all
taskRules / userPreferences / environmentFacts evidence):

- held-out citations in train-only claims: 0
- held-out citations in dream evidence: 0
- held-out citations in the new specs: 0 (two cross-references to t0397 found
  in the t0720 spec were reworded to task-name references and re-checked)

**Result: PASS.**

## Tasks recommended for replacement from the candidate pool

Four held-out trajectories ended FAIL with a bare verifier result and no
feedback, so the accepted answer / graded criterion cannot be reconstructed
honestly from available evidence:

1. **t0124** (Brazil 2027 EBITDA scenario) — the recorded interpretation was
   rejected; correct interpretation unknown.
2. **t0339** (Accretion/Dilution revised implied EV) — recorded value
   $25,136.14M was rejected; correct value unknown.
3. **t0157** (Anko typed bindings) — implementation self-tested clean but
   graded FAIL; discrepancy unknown.
4. **t0397 / t0720** (maintainer-ask) — protocol apparently followed through
   final handoff, still FAIL; criterion unknown. t0720 is also 414 steps, the
   longest in the curated set.

If any of these are kept, a container re-run that captures the verifier's
failure detail is the only way to make the spec honest.

---

# v2 refresh: swaps verified both ways (2026-11-01)

The v2 curation (see `docs/curated-tasks.json` revisionNote) dropped t0124,
t0339, and t0720 (unverifiable FAILs) and added **t0188** and **t0611**, both
PASS trajectories with recorded verifier evidence. Their spec files are new:

| Task | Spec | Verifier type | Both-ways status |
|---|---|---|---|
| t0188 | `tasks/t0188-prometheus-labelsort.json` | repo-issue-contract | verified both ways (2026-11-01) |
| t0611 | `tasks/t0611-vulture-cache.json` | repo-issue-contract | verified both ways (2026-11-01) |

## t0188 — prometheus sort_by_label typed comparison

- **Informed variant** = the PASS run's `promql/labelsort.go`, recovered
  verbatim from the trajectory (`src/verifier-assets/t0188-labelsort-informed/`),
  stdlib-only.
- **Naive variant** = natural-sort-only comparator (the pre-existing
  facette/natsort behavior the issue replaces).
- **Grader** = an independently authored contract test
  (`src/verifier-assets/t0188-labelsort-contract/labelsort_contract_test.go`),
  built only from the issue text. Result: informed passes all 8 test
  functions; naive fails 6 of 8. The check discriminates.
- Full-repo integration (functions.go wiring, go.mod/docs cleanup, hidden
  verifier tests) stays **container-required** and is skipped, not faked.
- The local eval runs the task in a standalone Go module with a pinned
  `CompareLabelValues` entry point (documented in the spec's environment) —
  the local equivalent of the container's hidden test surface.

## t0611 — vulture incremental cache

- **Informed variant** = the PASS run's implementation replayed verbatim
  against the pinned base commit ef9e6de
  (`src/verifier-assets/t0611-cache-informed/`): the replay applies clean,
  compiles, and the run's own reproduce script passes its assertions.
- **Naive variant** = flags accepted (`--cache`, `--cache-clear`,
  `--cache-dir`), `vulture.cache` exists, but nothing ever persists — the
  classic no-memory trap.
- **Grader** = an independently authored stdlib contract script
  (`src/verifier-assets/t0611-cache-contract/verifier-check.py`, 11 checks:
  reuse, transitive invalidation, backup+meta sha256, corruption warning,
  checksum mismatch, silent missing cache, settings/version invalidation,
  deleted-file cleanup, CLI flags, KeyboardInterrupt partial-save).
  Result: informed passes 11/11; naive fails 7/11. The check discriminates.
- The full pytest/ruff suite stays **container-required**.

Both-ways evidence is machine-generated by `python3 src/naive_baseline.py`
(zero API spend) and stored in `docs/naive-baseline-report.json`.

## READY for the first local eval (v2)

- **t0505** (Word2Vec component, 8 locally graded checks; informed reference
  solution passes 8/8, naive 1/8)
- **t0611** (vulture cache, 11 locally graded checks)
- **t0188** (label comparator contract, 8 locally graded test functions)

All other curated tasks remain container-required (hidden tests, workbook
readback, world-MCP sources, pandas source build) and are recorded as
skipped in eval results — never faked.
