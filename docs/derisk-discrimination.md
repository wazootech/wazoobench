# De-risk: what the expanded task set would actually test

Question: is the reactive (RDF/SPARQL procedural) memory system limited in a
way the current 3-task eval can't see, and would the 16 container-gated tasks
reveal it?

## Classification result: the expanded set does NOT discriminate

**13 of 19 gated tasks are trap-shaped** — the task re-encounters environment
constraints, tool quirks, or verifier conventions the corpus already recorded
known-failures for. Only **1 is synthesis-shaped** (t0174, pandas speedup:
requires composing a fresh optimization strategy under a new verifier), 5 mixed.

And the families behind those 13 trap-shaped tasks carry exactly the species
of knowledge that produced our one confirmed memory win (t0611: the
known-failures entry named the trap verbatim, and the memory arm avoided it
while the control fell in):

- **MCP workplace (7 gated tasks)**: tab_index API contract, answers-in-chat,
  verified-records-only — 5 rules + 4 known-failures, all trap-shaped.
- **Repo conventions (5 gated tasks)**: verified-records-only, no-fabrication,
  sandbox layout — 5 rules + 6 known-failures, trap-shaped.
- **DAPT (2)**: metric-scoping conventions (IPv4-only scoping, bucket
  definition) — recorded trap knowledge, trap-shaped.
- **SkillsBench/AlgoTune/dbt (4)**: command-duration limits, apply_patch tool,
  testbed quirks — trap-shaped with 2 known-failures each.

## What this means for the two hypotheses

**H1 (reactive-memory limitation will show up):** NOT testable with this task
set. The gated tasks overwhelmingly reward trap-avoidance — the reactive
system's home turf. Running them would confirm what we already know (memory
helps where experience recorded the trap) and tell us nothing new.

**H2 (the recall/presentation fixes hold at scale):** YES, testable — the 13
trap-shaped tasks are a real generalization test of the fixed pipeline (new
families, new containers, same delivery). If the known-failures mechanism
fires on fresh families the way it fired on t0611, that's the scaling
evidence.

## The synthesis-shaped task that DOES discriminate

t0174 (pandas speedup) is the one gated task where the reactive memory should
be neutral-to-weak: it requires composing an optimization strategy, and the
family's known-failures are about *process* (apply_patch tool, budget
discipline), not about *what optimization to try*. Its memory arm vs control
is the single cleanest test of H1 available without building new tasks.

**Cheap discrimination plan:** unlock t0174's container FIRST (one task, one
family, verifier is mechanical — speedup ratio), run it memory-vs-control.
- Memory ≥ control: reactive memory composes at least adequately → H1
  unconfirmed, proceed to full unlock with confidence.
- Memory < control: reactive memory actively distracts on synthesis tasks →
  H1 confirmed, the ontology/generalization direction becomes the priority,
  and we know the presenter must gate strategy claims by confidence.
