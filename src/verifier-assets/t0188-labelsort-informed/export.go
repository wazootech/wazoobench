// Test-only shim: exposes the issue's comparator for the contract test.
package labelsort

// CompareLabelValues wraps the unexported comparator recorded in the PASS
// trajectory. In the real task the comparator is called from promql
// sort_by_label; here the contract test needs an exported entry point.
func CompareLabelValues(a, b string) int { return compareLabelValues(a, b) }
