#!/usr/bin/env bun
/**
 * Corpus-scale exposure check for the opt-in embedding pass (wazoobench#10):
 * how many task rules / preferences does it merge on the real train-only
 * claims, and what do the merges look like? No agent runs, no spend.
 *
 *   bun run scripts/consolidation-ab.ts --claims <state>/claims.json \
 *     --embedder ollama:nomic-embed-text --threshold 0.73 --out docs/runs/<dir>
 */
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { parseArgs } from "node:util"
import { buildDreamReport, type ClaimBinding } from "../src/dream"
import { consolidateByEmbedding } from "../src/embedding-consolidation"
import { loadEmbedder } from "../src/embedders"
import type { Claim } from "../src/extraction"

const { values } = parseArgs({
  options: {
    claims: { type: "string" },
    split: { type: "string", default: "docs/data-split.json" },
    embedder: { type: "string", multiple: true, default: [] },
    threshold: { type: "string", multiple: true, default: [] },
    sample: { type: "string", default: "12" },
    out: { type: "string" },
  },
})
const train = new Set((JSON.parse(await readFile(values.split!, "utf-8")) as { train: string[] }).train)
const claims = (JSON.parse(await readFile(values.claims!, "utf-8")) as { claims: Claim[] }).claims
const bindings: ClaimBinding[] = claims
  .filter((c) => train.has(c.trajId))
  .map((c) => ({ claimText: c.claimText, type: c.type, subject: c.subject, action: c.action, object: c.object,
    where: c.where, trajId: c.trajId, turn: c.turn, outcome: c.outcome, speaker: c.speaker, extractor: c.extractor }))
const extractors = [...new Set(bindings.map((b) => b.extractor))].join(", ")
const lines = [`# Corpus exposure: embedding consolidation pass`, ``,
  `${bindings.length} train-only claims (extractor: ${extractors}).`, ``,
  `| embedder | threshold | task rules before -> after | preferences before -> after | merges |`, `|---|---|---|---|---|`]
const samples: string[] = []
const specs = values.embedder as string[]
const thresholds = (values.threshold as string[]).map(Number)
for (let i = 0; i < specs.length; i++) {
  const embedder = await loadEmbedder(specs[i])
  const report = buildDreamReport(bindings)
  const before = [report.taskRules.length, report.userPreferences.length]
  const rules = await consolidateByEmbedding(report.taskRules, embedder, thresholds[i])
  const prefs = await consolidateByEmbedding(report.userPreferences, embedder, thresholds[i])
  const merges = [...rules.merges, ...prefs.merges]
  lines.push(`| ${specs[i]} | ${thresholds[i]} | ${before[0]} -> ${rules.items.length} | ${before[1]} -> ${prefs.items.length} | ${merges.length} |`)
  samples.push(``, `## Sample merges: ${specs[i]} @ ${thresholds[i]}`, ``)
  const step = Math.max(1, Math.floor(merges.length / Number(values.sample)))
  for (let j = 0; j < merges.length && samples.length < 4000; j += step) {
    const m = merges[j]
    const clip = (s: string) => s.replace(/\s+/g, " ").slice(0, 160).replace(/\|/g, "\\|")
    samples.push(`- ${m.score.toFixed(2)}: "${clip(m.kept)}" <= "${clip(m.absorbed)}"`)
  }
}
const md = [...lines, ...samples, ""].join("\n")
console.log(md)
if (values.out) {
  await mkdir(values.out, { recursive: true })
  await writeFile(join(values.out, "corpus-exposure.md"), md)
}
