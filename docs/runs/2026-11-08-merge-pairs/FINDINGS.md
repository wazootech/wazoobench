# 2026-11-08: embedding consolidation (wazoobench#10)

**Verdict: embeddings alone should not decide merges.** They catch nearly every
paraphrase, but they cannot tell "same rule" from "same topic, different
rule". On the real corpus they would collapse the memory. The design that works
on the pair set is two-stage: embeddings propose candidate pairs, and an LLM
judge confirms each one. The opt-in pass ships default-off, and nothing changes
for current runs.

## 1. Merge-pair test (40 hand-labeled pairs)

18 paraphrase pairs, 16 hard negatives (same library or topic, different
rule) and 6 easy negatives; see `test/fixtures/merge-pairs/pairs.json`.
Embedder thresholds are chosen leave-one-out, so no pair is scored with a
threshold tuned on it.

| method | P | R | F1 |
|---|---|---|---|
| lexical (production `consolidateSimilar`) | 0.75 | 0.17 | 0.27 |
| hash embedding (floor) | 0.62 | 0.72 | 0.67 |
| TF.js USE | 0.59 | 0.94 | 0.72 |
| Ollama nomic-embed-text | 0.58 | 1.00 | 0.73 |
| qwen2.5-coder:7b judge, every pair | 1.00 | 0.94 | 0.97 |
| **lexical OR (nomic ≥ 0.73 AND 7b judge)** | **0.94** | **0.94** | **0.94** |
| lexical OR (nomic ≥ 0.73 AND qwen2.5:3b judge) | 0.94 | 0.83 | 0.88 |

Mean cosine, paraphrase vs hard negative: USE 0.67 vs 0.59, nomic 0.83 vs
0.77. The distributions overlap. For example, n03 ("pytest needs the task
venv" vs "pytest -x stops at the first failure") scores 0.87 with nomic,
above most true paraphrases.

The pass's single false positive is n16, and it comes from the production
lexical rule, not from embeddings: "Always run the full test suite..." and
"Always commit your changes..." merge on overlap.

Details: `merge-pairs.md`, `merge-judge-*.md`.

## 2. Corpus exposure (21,430 train-only claims, no agent runs)

Effect of the pass at the pair-set thresholds:

| embedder | task rules | preferences |
|---|---|---|
| nomic @ 0.73 | 673 → 81 | 254 → 62 |
| USE @ 0.54 | 673 → 129 | 254 → 105 |

The sampled merges are mostly unrelated fragments, for example
`cargo check --all-features` ⇐ `cargo fmt --all -- --check`. Caveat: the only
claims.json on hand comes from the deterministic fallback extractor, which
produces noisier text than DeepSeek extraction. The DeepSeek-extracted claims
behind the 11-02 eval were not found locally. Details: `corpus-exposure.md`.

## 3. The motivating pair is still unsolved

t0212/t0643, as quoted in the 11-02 FINDINGS, are:

- "returns an empty Word2Vec model when no tokens remain"
- "Gensim raises RuntimeError when given an empty sentence list"

- **#4's symbol-anchor clustering does not pair them.** The two claims share
  one anchor (`empty`), and the rule needs two. `buildDreamReport` on just
  these two bindings yields two singleton task rules.
- **The 7b judge also says DIFFERENT, even with a prompt that names this exact
  failure/fix case.**

The two claims aren't duplicates. They are complementary halves of a rule (the
trap and the fix), so this is a **synthesis** step, not deduplication. No
dedup method should be expected to merge them.

## Not established

- **No pass@1 rerun.** It needs the DeepSeek-extracted claims and a DeepSeek
  key, and neither was available in this session.
- **The pair set is small and hand-written**, except for 5 pairs quoted from
  the corpus. Read the numbers as directional.
- **No OpenAI arm**, because no key was set. Hosted worlds-api only accepts
  OpenAI 1536-dimension models, so that arm remains the hosted proxy to run.

## Options for next

1. **Two-stage consolidation in dream.** Embedding candidates (high recall)
   feed a judge using the extraction model already reachable in the sandbox
   (DeepSeek), with bounded calls. The candidate count per run decides the
   cost. Measure it against the pair set, then the corpus.
2. **A failure→fix synthesis pass.** Pair FAIL-provenance claims with
   PASS-provenance claims on the same API surface and have the LLM write the
   rule. This targets t0505 directly; consolidation does not.
3. **Fix the anchor gate.** `SYMBOL_RE` accepts any lowercase word of 4+
   characters (`returns`, `after`, `given`), so its "anchors" are mostly
   content words. Tightening the regex would lower false merges like n16, but
   it would not fix §3.
