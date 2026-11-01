#!/usr/bin/env bun
/**
 * Stratified train/held-out split of the v1.1 corpus trajectories.
 *
 * Input: the task-family map (fingerprint -> trajIds) produced by the
 * wazoo-frontiermemory family classifier, plus the rescued claims.json
 * (for trajectory inventory and outcome stats).
 * Output: docs/data/split.json — { train: string[], heldOut: string[], byFamily: {...} }
 *
 * Deterministic: seed fixed, sort before shuffle.
 */
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"

const SEED = 20261101
const HELDOUT_FRACTION = 0.1 // 75 of 750
const HELDOUT_MIN = 1 // every family keeps >=1 held-out when it has >=8 trajs

function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

async function main(args: string[]) {
  const [familyMapPath, claimsPath, outPath] = args
  if (!familyMapPath || !claimsPath || !outPath) {
    console.error("usage: bun scripts/split.ts <family-map.json> <claims.json> <out.json>")
    process.exit(2)
  }
  const famMap = JSON.parse(await readFile(familyMapPath, "utf8")) as Record<string, string[]>
  const claims = JSON.parse(await readFile(claimsPath, "utf8")) as {
    claims: { trajId: string; outcome: string }[]
    trajectories: unknown[]
  }

  const allTrajs = [...new Set(claims.claims.map((c) => c.trajId))].sort()
  const rng = mulberry32(SEED)

  // shuffle family-internal order deterministically
  const shuffle = <T,>(arr: T[]): T[] => {
    const a = [...arr].sort()
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1))
      ;[a[i], a[j]] = [a[j], a[i]]
    }
    return a
  }

  const heldOut = new Set<string>()
  const byFamily: Record<string, { train: string[]; heldOut: string[] }> = {}
  const assigned = new Set<string>()

  for (const [fam, trajs] of Object.entries(famMap).sort(([a], [b]) => a.localeCompare(b))) {
    const fresh = shuffle(trajs).filter((t) => !assigned.has(t))
    const n = Math.max(fresh.length >= HELDOUT_MIN + 6 ? HELDOUT_MIN : 0, Math.round(fresh.length * HELDOUT_FRACTION))
    const ho = fresh.slice(0, n)
    const tr = fresh.slice(n)
    byFamily[fam] = { train: tr, heldOut: ho }
    for (const t of ho) heldOut.add(t)
    for (const t of fresh) assigned.add(t)
  }

  // unassigned trajectories: distribute deterministically, 10% held out
  const unassigned = shuffle(allTrajs.filter((t) => !assigned.has(t)))
  const unHo = unassigned.slice(0, Math.round(unassigned.length * HELDOUT_FRACTION))
  for (const t of unHo) heldOut.add(t)

  const train = allTrajs.filter((t) => !heldOut.has(t))
  const out = {
    seed: SEED,
    heldOutFraction: HELDOUT_FRACTION,
    train: train.sort(),
    heldOut: [...heldOut].sort(),
    byFamily: Object.fromEntries(
      Object.entries(byFamily).map(([f, v]) => [f, { train: v.train.sort(), heldOut: v.heldOut.sort() }]),
    ),
    stats: {
      total: allTrajs.length,
      train: train.length,
      heldOut: [...heldOut].length,
      families: Object.keys(byFamily).length,
    },
  }
  await mkdir(dirname(outPath), { recursive: true })
  await writeFile(outPath, JSON.stringify(out, null, 2) + "\n")
  console.log(
    `split: ${out.stats.train} train / ${out.stats.heldOut} held-out of ${out.stats.total} (${out.stats.families} families stratified)`,
  )
}

await main(process.argv.slice(2))
