# Memory

Learned from 1 agent trajectories (0 PASS, 0 FAIL, 1 unlabeled), organized by task family. At the start of a task, find the family below that matches the task's benchmark, tools, or harness and follow its rules first; otherwise follow the general rules. Every line below is imperative: follow it, and open the linked skill file for provenance before deviating.

## General working rules

### Rules

1. don't change anything. [1 trajs] — see `skills/rule-01-corrected-don-t-change-anything.md`
2. still don't schedule anything yet, i just wanted to see it. [1 trajs] — see `skills/rule-02-corrected-still-don-t-schedule-anything.md`

### User preferences

- no big headings or emojis. [1 trajs]
- don't change anything. [1 trajs]
- still don't schedule anything yet, i just wanted to see it. [1 trajs]

### Environment

- - `bun run dev` runs the source code. [1 trajs]
- `/connect` lets you use your own model API keys. [1 trajs]
- - **MemFS:** the agent's context is tracked in git and can sync to your own GitHub repo. [1 trajs]
- to grab the new commits i had to fetch more git history into the clone, but your files are untouched. [1 trajs]

## How this memory was built

- 15 claims extracted from the trajectory corpus into a provenance-carrying claim graph.
- Near-duplicate phrasings were consolidated; each unique rule appears once.
- Patterns recurring across trajectories were promoted here, organized by task family; rules backed mostly by failed runs also appear under the family's known failures.
- Provenance per claim: trajectory id, turn, and the trajectory's verifier result (PASS/FAIL).
