#!/usr/bin/env bun
/**
 * fetch-claims: pull the persisted extracted claims.json from the private
 * wazootech/wazoobench-data repo and verify it against its manifest
 * (SHA-256, size, claim count) before handing it to the pipeline with
 * --resume-from-claims, so a rerun never pays for extraction twice.
 *
 * Usage:
 *   bun run src/fetch-claims.ts --out /tmp/wb-mem            # fetch + verify
 *   bun run src/fetch-claims.ts --out /tmp/wb-mem --check    # verify only
 */
import { $ } from "bun"
import { createHash } from "node:crypto"
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import path from "node:path"

const REPO = "https://github.com/wazootech/wazoobench-data"

function sha256File(file: string): string {
  return createHash("sha256").update(readFileSync(file)).digest("hex")
}

function fail(msg: string): never {
  console.error(`fetch-claims: ${msg}`)
  process.exit(1)
}

const argv = process.argv.slice(2)
const outIdx = argv.indexOf("--out")
const outDir = outIdx >= 0 ? path.resolve(argv[outIdx + 1] ?? ".") : "."
const checkOnly = argv.includes("--check")

const claimsPath = path.join(outDir, "claims.json")
const manifestPath = path.join(outDir, "claims-manifest.json")

if (existsSync(claimsPath) && existsSync(manifestPath)) {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"))
  const actual = sha256File(claimsPath)
  if (actual === manifest.sha256) {
    console.log(
      `fetch-claims: verified existing claims.json (${manifest.claims_count} claims, sha256 ${actual.slice(0, 12)}...); no fetch needed`
    )
    process.exit(0)
  }
  fail(
    `existing claims.json does not match manifest (expected ${manifest.sha256.slice(0, 12)}..., got ${actual.slice(0, 12)}...); refusing to use it`
  )
}

if (checkOnly) fail("no claims.json/manifest present to verify")

// Fetch the release assets from the private repo. Uses the ambient gh/git
// credential path (GH_TOKEN). Release assets avoid git-LFS limits and any
// local git mirror staleness.
const tag = process.env.WAZOOBENCH_DATA_TAG || "v1"
rmSync(outDir, { recursive: true, force: true })
mkdirSync(outDir, { recursive: true })

const dl = async (assetName: string, dest: string) => {
  // Resolve the asset id via the API, then download with the octet-stream
  // Accept header (browser_download_url 404s without a real browser token).
  const rel = JSON.parse(
    new TextDecoder().decode(
      await Bun.spawnSync(["gh", "api", `repos/wazootech/wazoobench-data/releases/tags/${tag}`]).stdout
    )
  )
  const asset = (rel.assets ?? []).find((a: { name: string }) => a.name === assetName)
  if (!asset) fail(`asset ${assetName} not found on release ${tag}`)
  const p = Bun.spawnSync(
    ["gh", "api", `repos/wazootech/wazoobench-data/releases/assets/${asset.id}`,
     "-H", "Accept: application/octet-stream"]
  )
  if (p.exitCode !== 0) fail(`asset download failed: ${p.stderr.toString().slice(0, 200)}`)
  writeFileSync(dest, p.stdout)
}

await dl("claims-manifest.json", manifestPath)
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"))
await dl("claims.json", claimsPath)
const actual = sha256File(claimsPath)
if (actual !== manifest.sha256) {
  fail(`SHA-256 mismatch after fetch: manifest ${manifest.sha256}, actual ${actual}`)
}
if (manifest.claims_count) {
  const parsed = JSON.parse(readFileSync(claimsPath, "utf8"))
  const n = Array.isArray(parsed.claims) ? parsed.claims.length : 0
  if (n !== manifest.claims_count) fail(`claim count mismatch: manifest ${manifest.claims_count}, file ${n}`)
  console.log(
    `fetch-claims: fetched + verified ${n} claims (corpus ${manifest.corpus?.digest ?? "?"}, extractor ${manifest.extractor?.name ?? "?"})`
  )
} else {
  console.log(`fetch-claims: fetched + verified claims.json (sha256 ${actual.slice(0, 12)}...)`)
}
writeFileSync(manifestPath, JSON.stringify(manifest, null, 2))
