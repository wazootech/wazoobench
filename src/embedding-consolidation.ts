/**
 * Embedding-based consolidation (wazoobench#10): an opt-in pass that runs
 * AFTER the lexical `consolidateSimilar` and merges items whose texts are
 * close in embedding space, catching paraphrases that share few content words
 * (the t0212/t0643 empty-input pair behind the t0505 regression).
 *
 * Off by default; the dream phase only runs it when an embedder is supplied.
 */
import { mergeEvidence, type Consolidatable } from "./dream"

/** Minimal embedder seam, structurally compatible with the SDK's EmbeddingService. */
export interface TextEmbedder {
  embed(texts: string[]): Promise<ArrayLike<number>[]>
}

export interface EmbeddingMerge {
  kept: string
  absorbed: string
  score: number
}

export function cosine(a: ArrayLike<number>, b: ArrayLike<number>): number {
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  return na === 0 || nb === 0 ? 0 : dot / Math.sqrt(na * nb)
}

/**
 * Greedy merge, same contract as consolidateSimilar: the first item above
 * `threshold` cosine against a kept item merges into it, the shorter phrasing
 * wins, provenance unions. Each kept item is compared by the vector of the
 * text it was first kept with, so merges cannot drift the representative.
 */
export async function consolidateByEmbedding<T extends Consolidatable>(
  items: T[],
  embedder: TextEmbedder,
  threshold: number
): Promise<{ items: T[]; merges: EmbeddingMerge[] }> {
  if (items.length < 2) return { items, merges: [] }
  const vectors = await embedder.embed(items.map((i) => i.text))
  const kept: T[] = []
  const keptVectors: ArrayLike<number>[] = []
  const merges: EmbeddingMerge[] = []
  items.forEach((item, index) => {
    let best = -1
    let bestScore = threshold
    for (let i = 0; i < kept.length; i++) {
      const score = cosine(keptVectors[i], vectors[index])
      if (score >= bestScore) {
        best = i
        bestScore = score
      }
    }
    if (best < 0) {
      kept.push(item)
      keptVectors.push(vectors[index])
      return
    }
    const twin = kept[best]
    merges.push({ kept: twin.text, absorbed: item.text, score: bestScore })
    if (item.text.length < twin.text.length) {
      twin.key = item.key
      twin.text = item.text
    }
    twin.evidence = mergeEvidence(twin.evidence, item.evidence)
    twin.support = new Set(twin.evidence.map((e) => e.trajId)).size
    twin.claimTypes = [...new Set([...twin.claimTypes, ...item.claimTypes])]
  })
  return { items: kept, merges }
}
