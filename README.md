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
- [ ] Stratified split (train/held-out) from the v1.1 corpus lineage
- [ ] Train-only memory regeneration (zero tokens)
- [ ] Held-out task shortlist with dependency tags (for Ethan to curate)
- [ ] Runner (agent loop + bash tool, seeded memory, both arms)
- [ ] Scorer (pass@1 delta, turn/token cost, per-tag breakdown)

## Principles

1. **Verifiers are born trivial** — file exists, JSON field equals value,
   command output matches. Letta had to repair 53% of theirs; ours never ship
   ambiguous.
2. **The split is auditable** — every memory item carries trajId provenance;
   a lint proves no held-out trajectory contributed to the memory.
3. **Cheap to fail** — every stage after extraction is local and free.
