import { describe, expect, test } from "bun:test"
import { consolidateByEmbedding, cosine, type TextEmbedder } from "../src/embedding-consolidation"
import { parseArgs } from "../src/memory-index"

/** Fake embedder: each text maps to a fixed vector from the table. */
const table = (vectors: Record<string, number[]>): TextEmbedder => ({
  embed: async (texts) => texts.map((t) => vectors[t] ?? [0, 0, 1]),
})

const item = (key: string, text: string, trajId: string) => ({
  key,
  text,
  evidence: [{ trajId, turn: 1, outcome: "FAIL" as const }],
  support: 1,
  claimTypes: ["fact" as const],
})

describe("embedding consolidation (wazoobench#10)", () => {
  test("cosine handles zero vectors", () => {
    expect(cosine([1, 0], [1, 0])).toBeCloseTo(1)
    expect(cosine([0, 0], [1, 0])).toBe(0)
  })

  test("merges above threshold, keeps the shorter phrasing, unions provenance", async () => {
    const long = "Gensim raises RuntimeError when given an empty sentence list."
    const short = "Guard empty input before Word2Vec."
    const other = "Use UTC timestamps."
    const embedder = table({ [long]: [1, 0.1, 0], [short]: [1, 0.12, 0], [other]: [0, 1, 0] })
    const { items, merges } = await consolidateByEmbedding(
      [item("a", long, "t0643"), item("b", short, "t0212"), item("c", other, "t0001")],
      embedder,
      0.9
    )
    expect(items).toHaveLength(2)
    expect(items[0].text).toBe(short)
    expect(items[0].key).toBe("b")
    expect(items[0].support).toBe(2)
    expect(merges).toHaveLength(1)
    expect(merges[0].score).toBeGreaterThan(0.9)
  })

  test("below threshold nothing merges", async () => {
    const embedder = table({ x: [1, 0, 0], y: [0.6, 0.8, 0] })
    const { items, merges } = await consolidateByEmbedding(
      [item("x", "x", "t1"), item("y", "y", "t2")],
      embedder,
      0.9
    )
    expect(items).toHaveLength(2)
    expect(merges).toHaveLength(0)
  })

  test("CLI keeps the pass off unless an embedder is named", () => {
    expect(parseArgs(["dream"]).consolidationEmbedder).toBeUndefined()
    const on = parseArgs(["dream", "--consolidation-embedder", "ollama:nomic-embed-text", "--consolidation-threshold", "0.9"])
    expect(on.consolidationEmbedder).toBe("ollama:nomic-embed-text")
    expect(on.consolidationThreshold).toBe(0.9)
  })
})
