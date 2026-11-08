#!/usr/bin/env bun
/**
 * Merge-pair test (wazoobench#10): how well does each similarity method
 * decide "same rule, two phrasings" vs "different rule"?
 *
 *   bun run scripts/merge-pairs.ts --out docs/runs/<date>-merge-pairs \
 *     --embedder hash --embedder use:<modelDir> --embedder ollama:nomic-embed-text
 *
 * Methods: `lexical` is the production consolidateSimilar decision (content
 * overlap >= 0.75 or symbol-anchor rescue). Each embedder is scored by cosine;
 * its threshold is chosen leave-one-out (pick the best-F1 threshold on the
 * other pairs, classify the held-out pair) so the reported F1 is not tuned on
 * the pair it scores. `lexical+<embedder>` is what dream actually runs with
 * the opt-in pass: merge if either says merge.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { parseArgs } from "node:util"
import { consolidateSimilar } from "../src/dream"
import { cosine } from "../src/embedding-consolidation"
import { loadEmbedder } from "../src/embedders"

interface Pair { id: string; merge: boolean; kind: string; source: string; a: string; b: string }
interface Scores { tp: number; fp: number; fn: number; tn: number }

const THRESHOLDS = Array.from({ length: 70 }, (_, i) => 0.3 + i * 0.01)

function lexicalMerges(a: string, b: string): boolean {
  const item = (key: string, text: string) => ({ key, text, evidence: [], support: 1, claimTypes: [] })
  return consolidateSimilar([item("a", a), item("b", b)]).length === 1
}

function tally(pairs: Pair[], decide: (p: Pair, i: number) => boolean): Scores {
  const s = { tp: 0, fp: 0, fn: 0, tn: 0 }
  pairs.forEach((p, i) => {
    const d = decide(p, i)
    if (d && p.merge) s.tp++
    else if (d) s.fp++
    else if (p.merge) s.fn++
    else s.tn++
  })
  return s
}

function f1(s: Scores) {
  const precision = s.tp + s.fp === 0 ? 1 : s.tp / (s.tp + s.fp)
  const recall = s.tp + s.fn === 0 ? 1 : s.tp / (s.tp + s.fn)
  const f = precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall)
  return { precision, recall, f1: f }
}

function bestThreshold(pairs: Pair[], scores: number[], skip: number): number {
  let best = THRESHOLDS[0]
  let bestF = -1
  for (const t of THRESHOLDS) {
    const s = tally(pairs, (_, i) => i !== skip && scores[i] >= t)
    // tally counts the skipped pair as a non-merge; remove it from the count.
    if (skip >= 0) pairs[skip].merge ? s.fn-- : s.tn--
    const f = f1(s).f1
    if (f > bestF) { bestF = f; best = t }
  }
  return best
}

const fmt = (x: number) => x.toFixed(2)

async function main() {
  const { values } = parseArgs({
    options: {
      pairs: { type: "string", default: "test/fixtures/merge-pairs/pairs.json" },
      out: { type: "string" },
      embedder: { type: "string", multiple: true, default: [] },
    },
  })
  const pairs = (JSON.parse(await readFile(values.pairs!, "utf-8")) as { pairs: Pair[] }).pairs
  const lexical = pairs.map((p) => lexicalMerges(p.a, p.b))
  const rows: Record<string, unknown>[] = []
  const perPair: Record<string, Record<string, number | boolean>> = {}
  for (const p of pairs) perPair[p.id] = { merge: p.merge, lexical: lexical[pairs.indexOf(p)] }

  const lexScores = tally(pairs, (_, i) => lexical[i])
  rows.push({ method: "lexical (production)", threshold: "-", ...lexScores, ...f1(lexScores) })

  for (const spec of values.embedder as string[]) {
    const started = performance.now()
    const embedder = await loadEmbedder(spec)
    const texts = [...new Set(pairs.flatMap((p) => [p.a, p.b]))]
    const vectors = await embedder.embed(texts)
    const vec = new Map(texts.map((t, i) => [t, vectors[i]]))
    const scores = pairs.map((p) => cosine(vec.get(p.a)!, vec.get(p.b)!))
    pairs.forEach((p, i) => (perPair[p.id][spec] = Number(scores[i].toFixed(3))))
    const loo = tally(pairs, (_, i) => scores[i] >= bestThreshold(pairs, scores, i))
    const global = bestThreshold(pairs, scores, -1)
    const combined = tally(pairs, (_, i) => lexical[i] || scores[i] >= bestThreshold(pairs, scores, i))
    const mean = (k: (p: Pair) => boolean) => {
      const xs = scores.filter((_, i) => k(pairs[i]))
      return xs.reduce((a, b) => a + b, 0) / xs.length
    }
    const seconds = (performance.now() - started) / 1000
    rows.push({ method: spec, threshold: `LOO (all-data best ${fmt(global)})`, ...loo, ...f1(loo),
      meanPos: mean((p) => p.merge), meanHardNeg: mean((p) => p.kind === "hard-negative"),
      meanEasyNeg: mean((p) => p.kind === "easy-negative"), seconds })
    rows.push({ method: `lexical+${spec}`, threshold: "LOO", ...combined, ...f1(combined) })
  }

  const header = "| method | threshold | P | R | F1 | tp/fp/fn/tn | mean cos pos / hard-neg / easy-neg |\n|---|---|---|---|---|---|---|"
  const table = rows.map((r) => {
    const means = r.meanPos === undefined ? "" :
      `${fmt(r.meanPos as number)} / ${fmt(r.meanHardNeg as number)} / ${fmt(r.meanEasyNeg as number)}`
    return `| ${r.method} | ${r.threshold} | ${fmt(r.precision as number)} | ${fmt(r.recall as number)} | ${fmt(r.f1 as number)} | ${r.tp}/${r.fp}/${r.fn}/${r.tn} | ${means} |`
  })
  const pairTable = Object.entries(perPair).map(([id, v]) =>
    `| ${id} | ${Object.values(v).map((x) => (typeof x === "number" ? fmt(x) : x ? "Y" : "-")).join(" | ")} |`)
  const cols = Object.keys(Object.values(perPair)[0])
  const md = [
    `# Merge-pair test (wazoobench#10)`, ``,
    `${pairs.length} pairs: ${pairs.filter((p) => p.merge).length} paraphrase, ` +
      `${pairs.filter((p) => p.kind === "hard-negative").length} hard-negative, ` +
      `${pairs.filter((p) => p.kind === "easy-negative").length} easy-negative.`, ``,
    header, ...table, ``,
    `## Per pair (cosine; lexical = production merge decision)`, ``,
    `| id | ${cols.join(" | ")} |`, `|${"---|".repeat(cols.length + 1)}`, ...pairTable, ``,
  ].join("\n")
  console.log(md)
  if (values.out) {
    await mkdir(values.out, { recursive: true })
    await writeFile(join(values.out, "merge-pairs.md"), md)
    await writeFile(join(values.out, "merge-pairs.json"), JSON.stringify({ rows, perPair }, null, 2))
  }
}

await main()
