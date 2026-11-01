// Contract test for t0188 (prometheus sort_by_label typed comparison).
// Authored independently from the issue text — this is NOT the recorded
// agent's own test file. It exercises only behaviors stated in the issue:
//
//   - class order: +Inf, finite numeric, -Inf, duration, bytes, semver,
//     IP, CIDR, timestamp, untyped natural
//   - leading whitespace group sorts before everything, natural within
//   - scientific exponents, leading plus, bare-exponent fallback, NaN fallback
//   - duration/bytes signed + scientific magnitudes, arbitrary precision
//   - semver optional v prefix, invalid forms fall back to natural
//   - IPv4 before IPv6, v4-mapped v6 counts as IPv6, CIDR equal addr ->
//     smaller prefix first
//   - equal typed values tie-break by natural order of original strings
//
// The solution under test must expose:
//
//	func CompareLabelValues(a, b string) int
//
// (a one-line exported wrapper over the issue's comparator is expected).
package labelsort

import "testing"

var classOrderCases = []struct {
	name  string
	items []string
}{
	{
		name:  "class_order_full",
		items: []string{"2024-01-02T00:00:00Z", "10.0.0.0/16", "10.0.0.1", "v1.2.3", "1KiB", "1KB", "500ms", "2s", "-Inf", "10", "+Inf", "abc", " leading"},
	},
	{
		name:  "leading_whitespace_first",
		items: []string{" z", " 9", "1", "abc"},
	},
	{
		name:  "numeric_forms",
		items: []string{"1e", "NaN", "+2", "10", "1e3", "1000", "2"},
	},
	{
		name:  "durations_and_bytes",
		items: []string{"2s", "1.5e3ms", "1KB", "1KiB", "-500ms"},
	},
	{
		name:  "semver_prefix_and_fallback",
		items: []string{"v1.9.0", "v1.10.0", "1.2.3.4", "v1.2.3-alpha", "v1.2.3"},
	},
	{
		name:  "ip_and_cidr",
		items: []string{"::ffff:1.2.3.4", "1.2.3.4", "::1", "10.0.0.0/16", "10.0.0.0/8", "10.0.0.0/24"},
	},
}

func sortReference(items []string) []string {
	out := append([]string(nil), items...)
	// insertion sort using CompareLabelValues — no dependence on sort pkg
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && CompareLabelValues(out[j], out[j-1]) < 0; j-- {
			out[j], out[j-1] = out[j-1], out[j]
		}
	}
	return out
}

func TestClassOrderFull(t *testing.T) {
	items := classOrderCases[0].items
	got := sortReference(items)
	want := []string{
		" leading",
		"+Inf",
		"10",
		"-Inf",
		"500ms", "2s",
		"1KB", "1KiB",
		"v1.2.3",
		"10.0.0.1",
		"10.0.0.0/16",
		"2024-01-02T00:00:00Z",
		"abc",
	}
	// The issue requires the exact sequence above: classes in the stated
	// order, ties broken naturally. Verify pairwise, not just total order.
	if len(got) != len(want) {
		t.Fatalf("length mismatch: got %v want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			// tolerate only *natural-tie* swaps between equal typed values
			if i > 0 && CompareLabelValues(got[i], got[i-1]) == 0 {
				continue
			}
			t.Fatalf("position %d: got %q want %q (full: %v)", i, got[i], want[i], got)
		}
	}
}

func TestLeadingWhitespaceGroup(t *testing.T) {
	got := sortReference([]string{" z", " 9", "1", "abc"})
	want := []string{" 9", " z", "1", "abc"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pos %d: got %v want %v", i, got, want)
		}
	}
}

func TestNumericForms(t *testing.T) {
	// scientific exponent and leading plus are numeric: "1e3" == "1000"
	// (tie -> natural), "+2" < "10"; bare exponent "1e" and "NaN" are
	// untyped natural and must sort among untyped strings, not numbers.
	got := sortReference([]string{"1e", "NaN", "+2", "10", "1e3", "1000", "2"})
	want := []string{"+2", "2", "10", "1e3", "1000", "1e", "NaN"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pos %d: got %v want %v", i, got, want)
		}
	}
	// natural tie-break: 1e3 vs 1000 compare equal typed -> natural digit-run
	// compare: "1" vs "1000"... the significant run "1000" has 4 digits vs 1,
	// so "1e3" sorts before "1000".
	if CompareLabelValues("1000", "1e3") <= 0 {
		t.Fatalf("tie-break failed: 1e3 must sort before 1000 (natural)")
	}
}

func TestDurationsAndBytes(t *testing.T) {
	// 1.5e3ms == 1500ms < 2s; 1KB (1000) < 1KiB (1024); -500ms is a duration
	got := sortReference([]string{"2s", "1.5e3ms", "1KB", "1KiB", "-500ms"})
	want := []string{"-500ms", "1.5e3ms", "2s", "1KB", "1KiB"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pos %d: got %v want %v", i, got, want)
		}
	}
}

func TestSemverPrefixAndFallback(t *testing.T) {
	got := sortReference([]string{"v1.9.0", "v1.10.0", "1.2.3.4", "v1.2.3-alpha", "v1.2.3"})
	want := []string{"v1.2.3-alpha", "v1.2.3", "v1.9.0", "v1.10.0", "1.2.3.4"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pos %d: got %v want %v", i, got, want)
		}
	}
}

func TestIPAndCIDR(t *testing.T) {
	got := sortReference([]string{"::ffff:1.2.3.4", "1.2.3.4", "::1", "10.0.0.0/16", "10.0.0.0/8", "10.0.0.0/24"})
	want := []string{"1.2.3.4", "::1", "::ffff:1.2.3.4", "10.0.0.0/8", "10.0.0.0/16", "10.0.0.0/24"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("pos %d: got %v want %v", i, got, want)
		}
	}
}

func TestBigPrecisionNoLoss(t *testing.T) {
	// 1e30 vs 1.0000000000000000000000000000001e30 — exact decimal compare
	small := "1e30"
	big := "1.0000000000000000000000000000001e30"
	if CompareLabelValues(small, big) >= 0 {
		t.Fatalf("precision lost: %q must sort before %q", small, big)
	}
	// arbitrarily large exponents must not lose order
	huge1 := "1e1000000000000000000"
	huge2 := "1e1000000000000000001"
	if CompareLabelValues(huge1, huge2) >= 0 {
		t.Fatalf("huge exponent order lost")
	}
}

func TestTotalOrderAntisymmetry(t *testing.T) {
	values := []string{"10", "10.0", "1e1", "+Inf", "-Inf", "5ms", "5B", "v1.0.0", "1.1.1.1", "1.1.1.1/32", "1970-01-01T00:00:00Z", "z", " x", "", "2", "0x10", "y"}
	for _, a := range values {
		for _, b := range values {
			ab := CompareLabelValues(a, b)
			ba := CompareLabelValues(b, a)
			if (ab < 0) != (ba > 0) {
				t.Fatalf("not antisymmetric: %q vs %q -> %d / %d", a, b, ab, ba)
			}
			if a == b && ab != 0 {
				t.Fatalf("self-compare nonzero for %q", a)
			}
		}
	}
}
