# 2026-11-02 A/B findings — hybrid delivery

**pass@1: memory 67% = control 67%.** But the aggregate hides per-task churn:
t0188 tie, **t0505 REGRESSION** (control PASS, memory FAIL), t0611 improvement.

## The t0505 regression is the finding

The memory arm spent 31 turns chasing a prove/verify strategy the presenter
block described — a strategy earned on t0611-class tasks, wrong for t0505.
The control arm, unburdened, just solved the task. The presenter block
carried task-specific strategy claims as if they were family-level rules.

## Implications

1. **Presenter blocks need per-claim confidence weighting** — rules with
   multi-trajectory support vs strategy claims earned on single tasks must be
   distinguishable at injection time.
2. **Task identifiers in provenance must never leak into presenter rules.**
   The presenter renders from MEMORY.md, whose lines cite skills paths —
   those are fine — but any task-named claim text is a t0611/t0505-specific
   shortcut masquerading as a rule.
3. This is exactly the §5 downgrade discipline from the ontology draft
   (never generalize past the evidence), violated at the render layer.

## Runner fix in the same pass

The hybrid delivery itself (inject rules + seed the folder + name the
concrete path) is committed: pure injection left the agent hunting for
nonexistent paths (3/3 FAIL in the first presenter attempt); pure pointer
delivery left the memory unread (iter2). Hybrid is the delivery that works.
