#!/usr/bin/env bun
/**
 * Held-out task candidates: for each held-out trajectory, extract the task
 * prompt (the user's task-defining message), the trajectory's outcome, family,
 * and dependency-tag evidence from TRAIN-side claims of the same family.
 */
import { readFile, writeFile, mkdir } from "node:fs/promises"
import { join, dirname } from "node:path"

const [corpusDir, splitPath, trainClaimsPath, outPath] = process.argv.slice(2)
const split = JSON.parse(await readFile(splitPath, "utf8"))
const trainState = JSON.parse(await readFile(trainClaimsPath, "utf8"))

// corpus files for held-out trajectories
const files = []
for (const dir of await Array.fromAsync(new Bun.Glob("*.json*").scan({ cwd: corpusDir }))) {
  files.push(dir)
}
const held = new Set(split.heldOut)
const famOf = new Map<string, string>()
for (const [fam, v] of Object.entries(split.byFamily)) for (const t of v.heldOut) famOf.set(t, fam)

// task prompt heuristics per format (ATIF: first user step with real length;
// jsonl: first response_item user message; opencode: first user message)
async function firstUserMessage(path: string): Promise<{ text: string; turn: number } | undefined> {
  const raw = await readFile(path, "utf8")
  if (path.endsWith(".json")) {
    try {
      const doc = JSON.parse(raw)
      if (doc.steps) {
        for (const s of doc.steps) {
          if (s.source === "user" && typeof s.message === "string" && s.message.trim().length > 40 && !s.message.startsWith("# Verifier")) {
            const stripped = s.message.replace(/<environment_context>[\s\S]*?<\/environment_context>/, "").trim()
            if (stripped.length > 40) return { text: stripped.slice(0, 600), turn: s.step_id }
          }
        }
      }
      if (doc.messages) {
        for (const m of doc.messages) {
          const text = (m.parts ?? []).filter((p: any) => p.type === "text").map((p: any) => p.text).join(" ")
          if (m.role === "user" && text.trim().length > 40) return { text: text.slice(0, 600), turn: 1 }
        }
      }
    } catch { return undefined }
  } else {
    const lines = raw.split("\n").filter(Boolean)
    let turn = 0
    for (const line of lines) {
      turn++
      try {
        const e = JSON.parse(line)
        const p = e.payload ?? e
        const text = p.text ?? (p.content ?? []).filter((c: any) => c.type === "input_text").map((c: any) => c.text).join(" ")
        if (p.role === "user" && typeof text === "string" && text.trim().length > 40 && !text.startsWith("# Verifier")) {
          const stripped = text.replace(/<environment_context>[\s\S]*?<\/environment_context>/, "").trim()
          if (stripped.length > 40) return { text: stripped.slice(0, 600), turn }
        }
      } catch { continue }
    }
  }
  return undefined
}

const candidates: any[] = []
const famDir = join(corpusDir)
const allFiles = [...(await Array.fromAsync(new Bun.Glob("t*.json*").scan({ cwd: corpusDir })))].sort()
for (const file of allFiles) {
  const trajId = file.replace(/\.json(l)?$/, "")
  if (!held.has(trajId)) continue
  const prompt = await firstUserMessage(join(corpusDir, file))
  const fam = famOf.get(trajId) ?? "unassigned"
  // train-side family claims: what the memory would carry for this family
  const famClaims = trainState.claims.filter((c: any) => c.trajId !== trajId).length
  candidates.push({ trajId, family: fam, prompt: prompt?.text ?? "(none found)", promptTurn: prompt?.turn ?? null, file })
}
// Dependency tags (Letta taxonomy) from prompt signals:
// task: omitted conventions/contracts; user: preference statements;
// environment: tool/availability/container facts
function dependencyTags(prompt: string, family: string): string[] {
  const tags = new Set<string>()
  const p = prompt.toLowerCase()
  if (/\b(format|convention|should|must|always|never|exactly|only)\b/.test(p)) tags.add("task")
  if (/\b(preference|prefer|style|round|decimal|summarize|report|chat|file)\b/.test(p)) tags.add("user")
  if (/\b(direc|path|env|available|installed|python|venv|tool|command|container|workspace)\b/.test(p)) tags.add("environment")
  if (tags.size === 0) tags.add("task") // tasks are memory-dependent by default in this corpus
  return [...tags].sort()
}
for (const c of candidates) c.tags = dependencyTags(c.prompt, c.family)
for (const c of candidates) {
  if (/^Feedback for the next attempt:/i.test(c.prompt)) { c.excluded = "feedback-continuation, not a fresh task prompt" }
}
candidates.sort((a, b) => a.family.localeCompare(b.family) || a.trajId.localeCompare(b.trajId))
await mkdir(dirname(outPath), { recursive: true })
await writeFile(outPath, JSON.stringify(candidates, null, 2) + "\n")
console.log(`candidates: ${candidates.length} held-out trajectories; with prompts: ${candidates.filter((c) => c.prompt !== "(none found)").length}`)
