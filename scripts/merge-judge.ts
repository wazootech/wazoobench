#!/usr/bin/env bun
/**
 * Merge-pair test, two-stage arm (wazoobench#10): embeddings propose
 * candidates (cosine >= --candidate-threshold), an LLM judge confirms.
 * Final decision = lexical OR (candidate AND judge says same rule).
 *
 *   bun run scripts/merge-judge.ts --embedder ollama:nomic-embed-text \
 *     --candidate-threshold 0.73 --judge qwen2.5-coder:7b --out docs/runs/<dir>
 *
 * The judge runs on local Ollama (OLLAMA_HOST), temperature 0.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { parseArgs } from "node:util"
import { consolidateSimilar } from "../src/dream"
import { cosine } from "../src/embedding-consolidation"
import { loadEmbedder } from "../src/embedders"

interface Pair { id: string; merge: boolean; kind: string; a: string; b: string }

const PROMPT = (a: string, b: string) => `Two memory claims were extracted from agent trajectories.
Decide whether they state the SAME rule or fact, so that one memory line could replace both
without losing information. Claims about the same library or topic that state DIFFERENT
requirements are NOT the same. Two claims describing one contract from opposite sides
(the failure and its fix) ARE the same.

Claim A: ${a}
Claim B: ${b}

Answer with exactly one word: SAME or DIFFERENT.`

async function judge(model: string, a: string, b: string): Promise<boolean> {
  const host = (process.env.OLLAMA_HOST ?? "http://localhost:11434").replace(/\/$/, "")
  const res = await fetch(`${host}/api/generate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model, prompt: PROMPT(a, b), stream: false, options: { temperature: 0 } }),
  })
  if (!res.ok) throw new Error(`ollama generate failed: HTTP ${res.status}`)
  return /\bSAME\b/i.test(((await res.json()) as { response: string }).response)
}

function lexicalMerges(a: string, b: string): boolean {
  const item = (key: string, text: string) => ({ key, text, evidence: [], support: 1, claimTypes: [] })
  return consolidateSimilar([item("a", a), item("b", b)]).length === 1
}

function score(pairs: Pair[], decisions: boolean[]) {
  let tp = 0, fp = 0, fn = 0, tn = 0
  pairs.forEach((p, i) => (decisions[i] ? (p.merge ? tp++ : fp++) : p.merge ? fn++ : tn++))
  const precision = tp + fp ? tp / (tp + fp) : 1
  const recall = tp + fn ? tp / (tp + fn) : 1
  return { tp, fp, fn, tn, precision, recall, f1: precision + recall ? (2 * precision * recall) / (precision + recall) : 0 }
}

const { values } = parseArgs({
  options: {
    pairs: { type: "string", default: "test/fixtures/merge-pairs/pairs.json" },
    embedder: { type: "string", default: "ollama:nomic-embed-text" },
    "candidate-threshold": { type: "string", default: "0.73" },
    judge: { type: "string", default: "qwen2.5-coder:7b" },
    out: { type: "string" },
  },
})
const pairs = (JSON.parse(await readFile(values.pairs!, "utf-8")) as { pairs: Pair[] }).pairs
const t = Number(values["candidate-threshold"])
const embedder = await loadEmbedder(values.embedder!)
const started = performance.now()
const vectors = await embedder.embed(pairs.flatMap((p) => [p.a, p.b]))
const cos = pairs.map((_, i) => cosine(vectors[2 * i], vectors[2 * i + 1]))
const judged: boolean[] = []
for (const p of pairs) judged.push(await judge(values.judge!, p.a, p.b))
const seconds = (performance.now() - started) / 1000
const lexical = pairs.map((p) => lexicalMerges(p.a, p.b))
const rows = {
  "judge alone (every pair)": score(pairs, judged),
  [`candidates: cos>=${t}`]: score(pairs, cos.map((c) => c >= t)),
  [`lexical OR (cos>=${t} AND judge)`]: score(pairs, pairs.map((_, i) => lexical[i] || (cos[i] >= t && judged[i]))),
}
const f = (x: number) => x.toFixed(2)
const md = [
  `# Two-stage merge test: ${values.embedder} candidates + ${values.judge} judge`, ``,
  `| arm | P | R | F1 | tp/fp/fn/tn |`, `|---|---|---|---|---|`,
  ...Object.entries(rows).map(([k, r]) => `| ${k} | ${f(r.precision)} | ${f(r.recall)} | ${f(r.f1)} | ${r.tp}/${r.fp}/${r.fn}/${r.tn} |`),
  ``, `Judge wall time for ${pairs.length} pairs (local): ${seconds.toFixed(1)}s`, ``,
  `| id | merge | cos | judge | final |`, `|---|---|---|---|---|`,
  ...pairs.map((p, i) => `| ${p.id} | ${p.merge ? "Y" : "-"} | ${f(cos[i])} | ${judged[i] ? "SAME" : "diff"} | ${lexical[i] || (cos[i] >= t && judged[i]) ? "merge" : "-"} |`),
].join("\n")
console.log(md)
if (values.out) {
  await mkdir(values.out, { recursive: true })
  const slug = values.judge!.replace(/[^\w.-]/g, "_")
  await writeFile(join(values.out, `merge-judge-${slug}.md`), md)
}
