package labelsort

import (
	"cmp"
	"strings"
)

// CompareLabelValues: naive baseline — plain natural sort for every value,
// the behavior the issue describes as "untyped string representations".
func CompareLabelValues(a, b string) int {
	return compareNatural(a, b)
}

func compareNatural(a, b string) int {
	ai, bi := 0, 0
	for ai < len(a) && bi < len(b) {
		if isDigit(a[ai]) && isDigit(b[bi]) {
			aEnd, bEnd := ai, bi
			for aEnd < len(a) && isDigit(a[aEnd]) {
				aEnd++
			}
			for bEnd < len(b) && isDigit(b[bEnd]) {
				bEnd++
			}
			aSig, bSig := ai, bi
			for aSig < aEnd && a[aSig] == '0' {
				aSig++
			}
			for bSig < bEnd && b[bSig] == '0' {
				bSig++
			}
			if ad, bd := aEnd-aSig, bEnd-bSig; ad != bd {
				return cmp.Compare(ad, bd)
			}
			if r := strings.Compare(a[aSig:aEnd], b[bSig:bEnd]); r != 0 {
				return r
			}
			ai, bi = aEnd, bEnd
			continue
		}
		if a[ai] != b[bi] {
			return cmp.Compare(a[ai], b[bi])
		}
		ai++
		bi++
	}
	if ai != len(a) || bi != len(b) {
		return cmp.Compare(len(a)-ai, len(b)-bi)
	}
	return strings.Compare(a, b)
}

func isDigit(c byte) bool { return c >= '0' && c <= '9' }
