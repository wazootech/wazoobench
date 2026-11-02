/**
 * checkAborted throws the signal's abort reason when the request has been
 * cancelled — the per-boundary cancellation check (issue #122). Evaluation
 * boundaries (per-pattern, per-join, per-update-operation) call it so an
 * aborted request stops at the next boundary instead of only at the
 * end-of-request reject race in WazooSparqlEngine.execute. A caller-provided
 * signal is forwarded into the engine's AbortController there, so the
 * thrown reason is the caller's Error (or the engine's "SPARQL query timed
 * out" / "SPARQL query aborted"), identical to what the race rejects with.
 */
export function checkAborted(signal: AbortSignal | undefined): void {
  if (signal !== undefined) {
    signal.throwIfAborted();
  }
}
