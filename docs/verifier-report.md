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
