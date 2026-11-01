# Wazoobench

Wazoo's owned memory-lift benchmark. It answers one question, cheaply and
repeatably: **does Wazoo memory make an agent pass more tasks?**

Pass@1 with memory vs. without, on held-out tasks the memory has provably
never seen — same agent, same model, deterministic verifiers. Runs locally or
on Modal in minutes, no Harbor tax.

## Design

```
corpus (750 trajs) ──► stratified split ──► train-only memory ──► held-out tasks
                        (675 train /          (dream on train      (10–20, with
                         75 held-out)          claims only, $0)     verifiers +
                                                                    dependency tags)
                                                                  ──► runner (agent + bash tool)
                                                                  ──► scorer (pass@1, with vs without)
```

The evidence trick: **memory generation is split into extract (expensive) and
dream (local, free)**. Filtering claims to train trajectories before graph
import produces a train-only memory at zero token cost, and the claim graph's
provenance (trajId on every claim) makes "never saw the held-out data"
machine-verifiable rather than promised.

Tasks carry a dependency tag from Letta's taxonomy — task / user / environment
memory — so results decompose into *which kind* of memory produces lift, not
just how much.

## Why this exists

FrontierMemory is the external-credibility channel (high rigor, high
overhead). Wazoobench is the internal channel: fast, cheap, CI-able, and
it doubles as a regression suite for every dream-phase curation change.
The two are complementary, not competing.

## Status

- [x] Name + repo
- [x] Stratified split (train/held-out) from the v1.1 corpus lineage (`docs/data-split.json`, seed 20261101)
- [x] Train-only memory regeneration (zero tokens; `/tmp/train-only-mem`, regenerable per the split doc)
- [x] Held-out task shortlist with dependency tags; v2 curation: 19 tasks, 3 unverifiable FAILs replaced by t0188 + t0611
- [x] Runner (agent loop + bash tool, seeded memory, both arms) — `src/runner.py`, reuses the deepseek_driver loop in-process
- [x] Scorer (pass@1 delta, turn/token cost, per-tag breakdown) — `src/eval.py`
- [x] Both-ways verifier checks on the swapped tasks (t0188, t0611) — `src/naive_baseline.py`, `docs/naive-baseline-report.json`

## Running the first eval

```sh
python3 src/eval.py --list      # what would run (no API spend)
bun run eval                    # the first PAID eval: 3 READY tasks x 2 arms
```

`bun run eval` maps to `python3 src/eval.py --memory /tmp/train-only-mem --model deepseek-v4-flash`.
READY tasks (locally verifiable without the task container): **t0505** (Word2Vec
component, generic python), **t0611** (vulture cache, clone + `pip install -e .`),
**t0188** (prometheus label comparator, standalone Go module with a pinned
`CompareLabelValues` entry point). Everything else stays container-required and
is recorded as skipped — never faked.

Each task gets: a DeepSeek balance pre-flight (abort under $1.00 remaining),
memory seeded by copying the folder into the workdir (the deepseek_driver
contract), max 30 turns, and a 400k-token ceiling per task (breach aborts with
`status=budget-aborted`). Results land in `docs/runs/<date>-eval/`
(`results.json` + `report.md`: pass@1 by arm, delta, by-family, by-tag,
per-task turns/tokens).

## Principles

1. **Verifiers are born trivial** — file exists, JSON field equals value,
   command output matches. Letta had to repair 53% of theirs; ours never ship
   ambiguous.
2. **The split is auditable** — every memory item carries trajId provenance;
   a lint proves no held-out trajectory contributed to the memory.
3. **Cheap to fail** — every stage after extraction is local and free.
