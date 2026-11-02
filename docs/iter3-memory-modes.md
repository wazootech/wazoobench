# Iteration 3: memory delivery modes

Iteration 2 finding (2026-11-02, docs/runs/2026-11-02-eval): with the budget
fixed at 800k tokens the control arm went 3/3 while the memory arm went 2/3
(t0505 regressed), and `memory_use` tracking showed the memory-arm agents read
MEMORY.md but opened **zero** skill files. The memory is present but inert —
the full-index "librarian" interface doesn't get the rules into working
context. Iteration 3 tests two delivery fixes, selected per run:

- `--memory-mode folder` (default) — iteration-2 behavior: the full MEMORY.md
  is dumped into the system prompt. Baseline for comparison.
- `--memory-mode family` — librarian fix: the seeded memory is pruned to the
  task family's sections plus the general rules, and `skills/` is pruned to
  the files those sections reference (t0505: ~4.8k of ~14.9k chars, 6 of
  ~1903 skill files kept). The driver contract is unchanged: it still reads
  MEMORY.md at the top of the folder — just a much shorter one.
- `--memory-mode inline` — presenter fix: the full index is NOT dumped; the
  family's sections are injected directly into the system prompt as
  imperatives ("The following memory rules apply to THIS task..."). The
  folder stays complete on disk for provenance.

Family mapping (spec `family` -> MEMORY.md section) lives in
`src/runner.py::FAMILY_TO_SECTION`; specs marked `unassigned` (the two
code-issue tasks in the READY set) map to the "Repo work conventions"
section plus general rules. The presenter block is built by
`inline_presenter_block()`; the pruned folder by `prune_memory_folder()`.
Result JSONs now carry `memory_mode` and `memory_stats` (chars retained,
skill files kept) so arm comparisons are self-describing.

## One-command run (costs ~$0.30 of DeepSeek credits — only on Ethan's go)

    cd ~/workspace/wazoobench
    python3 src/eval.py --memory-mode inline    # or --memory-mode family

Compare against the iter2 folder-mode numbers already in
docs/runs/2026-11-02-eval/. If both fixes still lose to the control, the
next hypothesis is memory content (the rules may not cover what these
specific tasks need), not delivery.
