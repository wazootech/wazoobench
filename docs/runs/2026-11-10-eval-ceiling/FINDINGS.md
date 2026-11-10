# Ceiling rerun (wazoobench#6/#7 acceptance), 2026-11-10

Per-task ceilings (1.6M on turn-heavy tasks) + family-slice inline injection.
Combined valid runs across same-day batches (17 runs, all completed or
budget-aborted at the raised ceiling):

| task | control | memory-inline |
|---|---|---|
| t0157 | PASS (budget-aborted, 66t) | PASS (completed, 73t) |
| t0188 | PASS (completed, 58t) | PASS (completed, 48t) |
| t0192 | PASS (completed, 60t) | PASS (completed, 77t) |
| t0443 | PASS (completed, 60t) | PASS (completed, 74t) |
| t0505 | PASS (completed, 72t) | FAIL (completed, 53t) |
| t0611 | PASS (completed, 60t) | PASS (completed, 70t) |
| t0663 | FAIL (completed, 60t) | FAIL (budget-aborted, 79t) |

**control 6/7 (86%), memory-inline 5/7 (71%).**

## Findings

1. **Censoring removed; memory no longer loses on budget.** At the 800k
   ceiling the memory arm budget-aborted on t0505/t0443/t0663 and lost
   checks it would otherwise have attempted. At 1.6M it *completes* on
   t0505 and t0443 (both arms converge on the same pass/fail verdicts
   except t0663).

2. **t0611 memory-positive signal now 4/4 across sessions.** The
   known-failures mechanism keeps steering the agent to the trap that
   control falls into.

3. **t0505 is now a clean negative.** With censoring gone, the memory arm
   completes (53t vs control 72t) and still fails its checks. Control
   passing while memory failing on the same task is the sharpest
   counterexample we have to "memory always helps"; the #11 embedding
   consolidation (t0212/t0643 paraphrase merge) is the candidate fix and
   its acceptance rerun targets exactly this task.

4. **t0663: neither arm passes.** Memory ran 79t and hit the ceiling; the
   task's own checks (hidden test suite on the mlflow monorepo) may need
   a task-specific ceiling or the tests are simply hard for the model at
   this size. Not a memory signal.

5. **Family-slice injection cost check:** memory arms used 2.0-2.6M tokens
   vs control 1.6-2.6M; the turn-tax gap narrowed (memory 73-79t vs
   control 58-72t on completed runs) but did not disappear. Slice
   injection did its job: no budget-abort from reading.

## Infrastructure notes

- Same-day reruns needed fresh workdirs (#18) and idempotent repo setup
  (#19/#20/#21, redelivered after a GitHub merge-propagation stall).
- t0007/t0174/t0414 prep still fail (issue #8 wheel bundle not wired).
- t0157 control was redelivered standalone after a transient 502.

Aggregate: memory 71% vs control 86% at n=7. The aggregate is still
against memory, driven by t0505; the family-scoped wins (t0611) and the
removed censoring are the design's supports, but the benchmark's
discriminating power now rests on whether #11's embedding merge can flip
t0505 without losing t0611.
