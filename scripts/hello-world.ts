#!/usr/bin/env bun
/**
 * Deterministically create and populate a "hello" world fixture.
 *
 * Works against any worlds-api endpoint (local dev server or hosted):
 *   bun scripts/hello-world.ts                       # http://localhost:8787, needs WORLDS_API_ADMIN_KEY
 *   WORLDS_DATA_URL=https://data.wazoo.dev \
 *   WORLDS_TOKEN=wzw_... WORLD_ID=w_... bun scripts/hello-world.ts   # bring your own world
 *
 * Local mode (no WORLDS_TOKEN): mints a namespace key from WORLDS_API_ADMIN_KEY,
 * creates the "hello" world if absent, seeds typed memories, verifies with SPARQL.
 * Hosted mode: uses the given world as-is.
 *
 * Deterministic: fixed memory set, fixed timestamps, fixed ids. Safe to re-run
 * (idempotent per statement: re-running adds no duplicates).
 */
import { readFile, writeFile, mkdir } from "node:fs/promises"
import { createHash } from "node:crypto"

const DATA_URL = (process.env.WORLDS_DATA_URL ?? "http://localhost:8787").replace(/\/+$/, "")
const ADMIN_KEY = process.env.WORLDS_API_ADMIN_KEY ?? ""
const TOKEN = process.env.WORLDS_TOKEN ?? ""
const WORLD_ID = process.env.WORLD_ID ?? ""
const STATE_FILE = process.env.HELLO_WORLD_STATE ?? ".hello-world.json"

const VOCAB = "https://wazoo.dev/vocab#"
const XSD = "http://www.w3.org/2001/XMLSchema#"
// Fixed stamp: the fixture is a reproducible artifact, not a journal.
const T0 = "2026-11-05T00:00:00Z"

const MEMORIES: Array<{ kind: string; statement: string }> = [
  { kind: "decision", statement: "Hello, world: this fixture verifies the local memory loop end to end" },
  { kind: "decision", statement: "Sample worlds are named hello, not smoke" },
  { kind: "preference", statement: "Ethan reviews fixture PRs before merge" },
  { kind: "person", statement: "Ethan Davidson founded Wazoo and manages the wazootech org" },
  { kind: "project", statement: "wazoobench is the Wazoo memory-lift benchmark (pass@1 with and without memory)" },
  { kind: "finding", statement: "worlds-api always requires a Bearer key; self-hosted users mint one locally" },
]

interface Seeded {
  worldId: string
  key: string
  mode: "local" | "byo"
  quads: number
}

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex")
}

function iriFor(kind: string, statement: string): string {
  // Named IRIs make re-runs idempotent: same statement, same subject, so a
  // re-import writes the same triples instead of adding blank-node duplicates.
  const hash = sha256(`${kind}|${statement}`).slice(0, 16)
  return `<${VOCAB}hello/${kind}-${hash}>`
}

function turtleFor(kind: string, statement: string): string {
  const esc = statement.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
  return [
    `@prefix wz: <${VOCAB}> .`,
    `@prefix xsd: <${XSD}> .`,
    `${iriFor(kind, statement)} a wz:${kind} ;`,
    `  wz:statement "${esc}" ;`,
    `  wz:recordedAt "${T0}"^^xsd:dateTime .`,
  ].join("\n") + "\n"
}

async function api(path: string, token: string, body: unknown): Promise<any> {
  const res = await fetch(`${DATA_URL}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status} ${text.slice(0, 200)}`)
  return text ? JSON.parse(text) : null
}

async function mintLocalKey(): Promise<string> {
  if (!ADMIN_KEY) {
    console.error("Local mode needs WORLDS_API_ADMIN_KEY (the .dev.vars value) or set WORLDS_TOKEN + WORLD_ID.")
    process.exit(1)
  }
  const res = await fetch(`${DATA_URL}/api-keys`, {
    method: "POST",
    headers: { Authorization: `Bearer ${ADMIN_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "hello-world-fixture", namespace: "hello" }),
  })
  if (!res.ok) throw new Error(`key mint failed: ${res.status} ${await res.text()}`)
  const data = await res.json() as { token: string }
  return data.token
}

async function createWorld(token: string): Promise<string> {
  // Data-plane create takes a FLAT body (displayName at top level); the
  // {"world": {...}} wrapper is the control-plane (api.wazoo.dev) shape.
  const data = await api("/worlds", token, { displayName: "hello" })
  return data.id
}

async function ensureWorldId(token: string): Promise<string> {
  if (WORLD_ID) return WORLD_ID
  const res = await fetch(`${DATA_URL}/worlds`, { headers: { Authorization: `Bearer ${token}` } })
  if (res.ok) {
    const list = await res.json() as { worlds?: Array<{ id: string; displayName: string; state?: string }> }
    const existing = (list.worlds ?? []).find(
      (w) => (w.displayName === "hello" || w.id === "hello") && (w.state ?? "active") === "active",
    )
    if (existing) return existing.id
  }
  return createWorld(token)
}

async function importTurtle(token: string, worldId: string, turtle: string): Promise<number> {
  const data = await api(`/worlds/${worldId}/import`, token, { data: turtle, contentType: "text/turtle" })
  return (data?.imported?.quads ?? 0) as number
}

async function sparql(token: string, worldId: string, query: string): Promise<any[]> {
  const data = await api(`/worlds/${worldId}/sparql`, token, { query })
  return data?.results?.bindings ?? []
}

async function main(): Promise<Seeded> {
  const mode = TOKEN ? "byo" : "local"
  const key = TOKEN || (await mintLocalKey())
  const worldId = await ensureWorldId(key)
  console.log(`hello world: ${worldId} (${mode}, ${DATA_URL})`)

  let quads = 0
  for (const { kind, statement } of MEMORIES) {
    quads += await importTurtle(key, worldId, turtleFor(kind, statement))
  }

  const check = await sparql(key, worldId,
    `PREFIX wz: <${VOCAB}>\nSELECT ?kind ?statement ?when WHERE { ?m a ?kind ; wz:statement ?statement ; wz:recordedAt "${T0}"^^<${XSD}dateTime> . } ORDER BY ?statement`)
  console.log(`seeded ${quads} quads; verified ${check.length} typed memories by SPARQL`)
  if (check.length < MEMORIES.length) {
    throw new Error(`fixture incomplete: ${check.length}/${MEMORIES.length} memories visible`)
  }

  await mkdir(new URL(".", `file://${process.cwd()}/`).pathname, { recursive: true }).catch(() => {})
  await writeFile(STATE_FILE, JSON.stringify({
    dataUrl: DATA_URL, worldId, mode,
    keyFingerprint: key ? sha256(key).slice(0, 12) : "",
    memoryCount: MEMORIES.length, t0: T0,
  }, null, 2) + "\n")
  console.log(`state written to ${STATE_FILE} (no key material, just a fingerprint)`)
  return { worldId, key, mode, quads }
}

main().catch((err) => {
  console.error(`hello-world failed: ${err instanceof Error ? err.message : err}`)
  process.exit(1)
})
