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
  if (kind === "openai") return openaiEmbedder(arg || "text-embedding-3-small")
  throw new Error(`unknown embedder spec: ${spec}`)
}
