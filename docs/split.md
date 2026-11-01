# Stratified train/held-out split

Splits the 750-trajectory corpus into 675 train / 75 held-out, stratified by
the task-family fingerprints wazoo-frontiermemory/src/families.ts established.
The split is deterministic: same inputs, same output, seeded shuffle.

## Held-out requirements

- Every family keeps at least one held-out trajectory (so no family's lift is
  unmeasurable).
- Held-out trajectories skew toward memory-heavy families (the ones whose
  curated memory items drew on those trajectories).
- Provenance lint: NO claim in the train-only memory may carry a held-out
  trajId. The lint is part of CI.
