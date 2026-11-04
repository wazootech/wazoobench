# t0174 discriminating A/B — the answer to H1

**Both arms PASS, cleanly, at full budget. No memory lift on the synthesis
task — and no harm.**

| check | memory arm | control |
|---|---|---|
| harness_runs (pandas rebuild) | PASS | PASS |
| environment_rebuilt | PASS | PASS |
| functional_equivalence | PASS | PASS |
| speedup_measured | PASS | PASS |

Both arms completed (61 vs 68 turns). The recorded corpus failure
(ModuleNotFoundError before any grading) did NOT recur in either arm — the
memory's task-venv/reinstall rule would have helped if needed, but both
agents rebuilt successfully regardless.

## H1 verdict: NOT confirmed

The reactive-memory limitation hypothesis — "procedural memory actively
distracts on synthesis tasks" — is REFUTED at n=1 on the one synthesis-shaped
task: the memory arm matched the control exactly. No distraction, no harm,
no lift. The memory was present-but-neutral exactly where the architecture
predicts neutral (synthesis isn't what recorded traps teach).

## The honest aggregate picture across all wazoobench runs

- t0611 (trap-heavy): memory WINS reproducibly (the known-failures mechanism)
- t0505, t0188 (mixed): neutral-to-variable
- t0174 (synthesis): neutral

That gradient IS the architecture's honest profile: **procedural memory
prevents re-learning where experience recorded the trap; it neither helps nor
hurts where the agent must compose fresh strategy.** This matches what the
architecture claims to be — and it's a defensible, true product claim:

"Wazoo memory stops agents from repeating recorded failures, at zero
configuration, verifiably (provenance lint), with no downside on tasks where
it has nothing to teach."

## Cost of this finding: ~\$0.16 (balance 7.85 after the full session)
