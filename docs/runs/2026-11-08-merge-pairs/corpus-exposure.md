# Corpus exposure: embedding consolidation pass

21430 train-only claims (extractor: fallback).

| embedder | threshold | task rules before -> after | preferences before -> after | merges |
|---|---|---|---|---|
| ollama:nomic-embed-text | 0.73 | 673 -> 81 | 254 -> 62 | 784 |
| use:tfjs-use | 0.54 | 673 -> 129 | 254 -> 105 | 693 |

Sampled merge texts are omitted here because the corpus is a gated dataset and this repository is public. Rerun the script locally to see them.
