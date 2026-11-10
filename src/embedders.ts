/**
 * Embedder adapters for consolidation and the merge-pair test (wazoobench#10).
 *
 * Spec strings: `hash`, `use:<modelDir>`, `ollama:<model>`, `openai:<model>`.
 * Ollama talks to OLLAMA_HOST (default http://localhost:11434); OpenAI needs
 * OPENAI_API_KEY. Neither is reachable inside the generation sandbox, so they
 * are for local measurement runs only.
 */
import type { TextEmbedder } from "./embedding-consolidation"
import { DeterministicEmbeddingService, loadTfjsUseEmbeddingService, withEmbeddingBatches } from "./graph"

/** nomic-embed-text is trained with task prefixes; clustering is our task. */
const OLLAMA_PREFIX: Record<string, string> = { "nomic-embed-text": "clustering: " }

function ollamaEmbedder(model: string): TextEmbedder {
  const host = (process.env.OLLAMA_HOST ?? "http://localhost:11434").replace(/\/$/, "")
  const prefix = OLLAMA_PREFIX[model.split(":")[0]] ?? ""
  return {
    async embed(texts) {
      const out: number[][] = []
      for (let i = 0; i < texts.length; i += 64) {
        const input = texts.slice(i, i + 64).map((t) => prefix + t)
        const res = await fetch(`${host}/api/embed`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ model, input }),
        })
        if (!res.ok) throw new Error(`ollama embed failed: HTTP ${res.status}`)
        out.push(...((await res.json()) as { embeddings: number[][] }).embeddings)
      }
      return out
    },
  }
}

/**
 * ONNX-backed embedder: shells out to scripts/onnx_embed.py (tokenizers +
 * onnxruntime, mean-pool + L2-normalize, sentence-transformers pooling
 * semantics). Spec: `onnx:<modelDir>` where modelDir holds model.onnx and
 * tokenizer.json. Chosen for wazoobench#10 after the labeled merge-pair
 * bake-off: all-MiniLM-L6-v2 scored 15/18 paraphrases merged (hard
 * negatives need the evidence-aware guard, see below).
 */
function onnxEmbedder(modelDir: string): TextEmbedder {
  const { spawnSync } = require("node:child_process") as typeof import("node:child_process")
  const path = require("node:path") as typeof import("node:path")
  const model = path.join(modelDir, "model.onnx")
  const tokenizer = modelDir
  let cache: Promise<Map<string, number[]>> | undefined
  const runBatch = (texts: string[]): Promise<Map<string, number[]>> =>
    new Promise((resolve, reject) => {
      const proc = spawnSync(
        "python3",
        [path.join(import.meta.dir, "..", "scripts", "onnx_embed.py")],
        { input: JSON.stringify({ model, tokenizer, texts }), maxBuffer: 1 << 26 },
      )
      if (proc.status !== 0) return reject(new Error(`onnx embed failed: ${proc.stderr.toString().slice(0, 200)}`))
      const { embeddings } = JSON.parse(proc.stdout.toString()) as { embeddings: number[][] }
      resolve(new Map(texts.map((t, i) => [t, embeddings[i]])))
    })
  return {
    async embed(texts) {
      // One process per call is fine here: consolidation is a batch job,
      // not a hot path. Cache within the call to dedupe repeated texts.
      cache ??= runBatch([...new Set(texts)])
      const map = await cache
      return texts.map((t) => map.get(t) ?? [0])
    },
  }
}

function openaiEmbedder(model: string): TextEmbedder {
  const key = process.env.OPENAI_API_KEY
  if (!key) throw new Error("openai embedder needs OPENAI_API_KEY")
  return {
    async embed(texts) {
      const out: number[][] = []
      for (let i = 0; i < texts.length; i += 64) {
        const res = await fetch("https://api.openai.com/v1/embeddings", {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
          body: JSON.stringify({ model, input: texts.slice(i, i + 64), dimensions: 1536 }),
        })
        if (!res.ok) throw new Error(`openai embed failed: HTTP ${res.status}`)
        const rows = ((await res.json()) as { data: { index: number; embedding: number[] }[] }).data
        out.push(...rows.sort((a, b) => a.index - b.index).map((r) => r.embedding))
      }
      return out
    },
  }
}

export async function loadEmbedder(spec: string): Promise<TextEmbedder> {
  const [kind, ...rest] = spec.split(":")
  const arg = rest.join(":")
  if (kind === "hash") return new DeterministicEmbeddingService()
  if (kind === "use") return withEmbeddingBatches(await loadTfjsUseEmbeddingService(arg)) as TextEmbedder
  if (kind === "ollama") return ollamaEmbedder(arg || "nomic-embed-text")
  if (kind === "onnx") return onnxEmbedder(arg)
  if (kind === "openai") return openaiEmbedder(arg || "text-embedding-3-small")
  throw new Error(`unknown embedder spec: ${spec}`)
}
