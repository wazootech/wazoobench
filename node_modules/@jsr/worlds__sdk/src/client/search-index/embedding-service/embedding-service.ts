/**
 * EmbeddingService defines the abstract projection interface required to map
 * textual inputs into continuous, high-dimensional dense vector representations
 * suitable for nearest-neighbor mathematical search traversal.
 */
export interface EmbeddingService {
  /**
   * embed performs external or local transformation of textual input sequences in batch.
   *
   * @param texts Array of clean input sequences targeted for vectorizing.
   * @returns Vector space projection arrays matching the input array index positioning.
   */
  embed(texts: string[]): Promise<Array<Float32Array | number[]>>;
}
