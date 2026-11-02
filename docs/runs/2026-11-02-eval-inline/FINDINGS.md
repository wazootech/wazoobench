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

## Post-run diagnosis (2026-11-02): the t0505 regression's actual root cause

The presenter-block-overconfidence hypothesis was WRONG. The real cause is
upstream: **the empty-input knowledge never became a memory rule at all.**

The claims exist — t0212 (PASS): "returns an empty Word2Vec model when no
tokens remain"; t0643 (FAIL): "Gensim raises RuntimeError when given an empty
sentence list" — but dream's clustering never promoted them into a task rule.
Why: the PASS claim and the FAIL claim are phrased differently enough that
Jaccard similarity (threshold 0.75) missed the pairing, and each stayed a
singleton. Two singletons = two skill files, zero index entries, zero
presenter lines.

Meanwhile the presenter's word2vec family block carries only environment
facts and preferences — nothing that would have prevented the failure.

**The fix this points at is not confidence-gating (the presenter never had a
bad rule to gate). It's recall**: the extraction→clustering pipeline is
dropping decisive, corpus-recorded knowledge because phrasing variance across
trajectories defeats text-similarity clustering. The t0643 FAIL claim
describes the exact trap; the t0212 PASS claim describes the exact fix. They
never met.

Options: (a) embedding-based clustering (the graph already has vector
search; use it in dream's consolidation), (b) LLM-assisted consolidation in
dream (bounded calls, cheap on DeepSeek), (c) a targeted "singleton rescue"
pass — claims from the same family citing the same API symbol (gensim,
Word2Vec, task_func) cluster together regardless of phrasing.
