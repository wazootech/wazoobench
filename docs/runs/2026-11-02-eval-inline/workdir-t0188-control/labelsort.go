// Copyright The Prometheus Authors
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package labelsort

import (
	"bytes"
	"math/big"
	"net/netip"
	"sort"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

// labelValueKind provides an ordering between independently parsed value
// domains. Keeping the domain in the parsed value is important: falling back
// to natural comparison whenever only one side parses would make the
// comparator non-transitive.
type labelValueKind uint8

const (
	labelValueLeadingWhitespace labelValueKind = iota
	labelValuePositiveInfinity
	labelValueNumber
	labelValueNegativeInfinity
	labelValueDuration
	labelValueBytes
	labelValueSemver
	labelValueIP
	labelValueCIDR
	labelValueTimestamp
	labelValueNatural
)

type parsedLabelValue struct {
	kind      labelValueKind
	number    exactDecimal
	magnitude exactValue
	version   semanticVersion
	address   netip.Addr
	prefix    netip.Prefix
	timestamp time.Time
}

// compareLabelValues compares label values in the human-oriented order used by
// sort_by_label. It always returns a strict three-way result: typed values that
// represent the same value are ordered naturally by their original spelling.
func compareLabelValues(a, b string) int {
	if a == b {
		return 0
	}

	pa := parseLabelValue(a)
	pb := parseLabelValue(b)
	if pa.kind != pb.kind {
		return compareValues(pa.kind, pb.kind)
	}

	var result int
	switch pa.kind {
	case labelValueNumber:
		result = pa.number.cmp(pb.number)
	case labelValueDuration, labelValueBytes:
		result = pa.magnitude.cmp(pb.magnitude)
	case labelValueSemver:
		result = pa.version.cmp(pb.version)
	case labelValueIP:
		result = compareAddresses(pa.address, pb.address)
	case labelValueCIDR:
		result = comparePrefixes(pa.prefix, pb.prefix)
	case labelValueTimestamp:
		result = compareTimestamps(pa.timestamp, pb.timestamp)
	}
	if result != 0 {
		return result
	}

	return compareNatural(a, b)
}

func parseLabelValue(value string) parsedLabelValue {
	if hasLeadingWhitespace(value) {
		return parsedLabelValue{kind: labelValueLeadingWhitespace}
	}

	if sign, ok := parseInfinity(value); ok {
		if sign > 0 {
			return parsedLabelValue{kind: labelValuePositiveInfinity}
		}
		return parsedLabelValue{kind: labelValueNegativeInfinity}
	}

	if number, ok := parseExactDecimal(value); ok {
		return parsedLabelValue{kind: labelValueNumber, number: number}
	}
	if duration, ok := parseScaledValue(value, durationUnits); ok {
		return parsedLabelValue{kind: labelValueDuration, magnitude: duration}
	}
	if byteCount, ok := parseScaledValue(value, byteUnits); ok {
		return parsedLabelValue{kind: labelValueBytes, magnitude: byteCount}
	}
	if version, ok := parseSemanticVersion(value); ok {
		return parsedLabelValue{kind: labelValueSemver, version: version}
	}
	if address, err := netip.ParseAddr(value); err == nil {
		return parsedLabelValue{kind: labelValueIP, address: address}
	}
	if prefix, err := netip.ParsePrefix(value); err == nil {
		return parsedLabelValue{kind: labelValueCIDR, prefix: prefix.Masked()}
	}
	if timestamp, err := time.Parse(time.RFC3339Nano, value); err == nil {
		return parsedLabelValue{kind: labelValueTimestamp, timestamp: timestamp}
	}
	return parsedLabelValue{kind: labelValueNatural}
}

func hasLeadingWhitespace(value string) bool {
	if value == "" {
		return false
	}
	r, _ := utf8.DecodeRuneInString(value)
	return unicode.IsSpace(r)
}

func parseInfinity(value string) (int, bool) {
	switch strings.ToLower(value) {
	case "inf", "+inf", "infinity", "+infinity":
		return 1, true
	case "-inf", "-infinity":
		return -1, true
	default:
		return 0, false
	}
}

// exactDecimal represents coefficient * 10^exponent. The coefficient is kept
// as canonical decimal digits so both it and the exponent can be arbitrarily
// large without converting through a floating-point type.
type exactDecimal struct {
	sign        int
	coefficient string
	exponent    big.Int
}

func parseExactDecimal(value string) (exactDecimal, bool) {
	number, end, ok := parseExactDecimalPrefix(value, 0)
	return number, ok && end == len(value)
}

func parseExactDecimalPrefix(value string, start int) (exactDecimal, int, bool) {
	var number exactDecimal
	if start >= len(value) {
		return number, start, false
	}

	i := start
	sign := 1
	if value[i] == '+' || value[i] == '-' {
		if value[i] == '-' {
			sign = -1
		}
		i++
		if i == len(value) {
			return number, start, false
		}
	}

	integerStart := i
	for i < len(value) && isASCIIDigit(value[i]) {
		i++
	}
	integerEnd := i

	fractionStart, fractionEnd := i, i
	if i < len(value) && value[i] == '.' {
		i++
		fractionStart = i
		for i < len(value) && isASCIIDigit(value[i]) {
			i++
		}
		fractionEnd = i
	}
	if integerStart == integerEnd && fractionStart == fractionEnd {
		return number, start, false
	}

	var parsedExponent big.Int
	if i < len(value) && (value[i] == 'e' || value[i] == 'E') {
		exponentMarker := i
		j := i + 1
		if j < len(value) && (value[j] == '+' || value[j] == '-') {
			j++
		}
		exponentDigits := j
		for j < len(value) && isASCIIDigit(value[j]) {
			j++
		}
		// An E can also begin a byte unit (EB or EiB). Only consume it as
		// an exponent when at least one exponent digit follows it.
		if j > exponentDigits {
			exponentText := value[exponentMarker+1 : j]
			if _, ok := parsedExponent.SetString(exponentText, 10); !ok {
				return number, start, false
			}
			i = j
		}
	}

	digits := value[integerStart:integerEnd] + value[fractionStart:fractionEnd]
	digits = strings.TrimLeft(digits, "0")
	if digits == "" {
		return exactDecimal{}, i, true
	}

	trailingZeros := len(digits) - len(strings.TrimRight(digits, "0"))
	digits = digits[:len(digits)-trailingZeros]

	number.sign = sign
	number.coefficient = digits
	number.exponent.Set(&parsedExponent)
	number.exponent.Sub(&number.exponent, new(big.Int).SetUint64(uint64(fractionEnd-fractionStart)))
	number.exponent.Add(&number.exponent, new(big.Int).SetUint64(uint64(trailingZeros)))
	return number, i, true
}

func (d exactDecimal) cmp(other exactDecimal) int {
	if d.sign != other.sign {
		return compareValues(d.sign, other.sign)
	}
	if d.sign == 0 {
		return 0
	}

	result := d.cmpAbs(other)
	if d.sign < 0 {
		return -result
	}
	return result
}

func (d exactDecimal) cmpAbs(other exactDecimal) int {
	dOrder := decimalOrder(&d.exponent, len(d.coefficient))
	otherOrder := decimalOrder(&other.exponent, len(other.coefficient))
	if result := dOrder.Cmp(otherOrder); result != 0 {
		return result
	}

	maxDigits := maxInt(len(d.coefficient), len(other.coefficient))
	for i := 0; i < maxDigits; i++ {
		dDigit, otherDigit := byte('0'), byte('0')
		if i < len(d.coefficient) {
			dDigit = d.coefficient[i]
		}
		if i < len(other.coefficient) {
			otherDigit = other.coefficient[i]
		}
		if dDigit != otherDigit {
			return compareValues(dDigit, otherDigit)
		}
	}
	return 0
}

func decimalOrder(exponent *big.Int, digits int) *big.Int {
	return new(big.Int).Add(exponent, new(big.Int).SetUint64(uint64(digits)))
}

type scaledUnit struct {
	suffix string
	factor *big.Int
}

var durationUnits = []scaledUnit{
	{suffix: "ms", factor: big.NewInt(1_000_000)},
	{suffix: "ns", factor: big.NewInt(1)},
	{suffix: "us", factor: big.NewInt(1_000)},
	{suffix: "µs", factor: big.NewInt(1_000)},
	{suffix: "μs", factor: big.NewInt(1_000)},
	{suffix: "s", factor: big.NewInt(1_000_000_000)},
	{suffix: "m", factor: big.NewInt(60_000_000_000)},
	{suffix: "h", factor: big.NewInt(3_600_000_000_000)},
	{suffix: "d", factor: big.NewInt(86_400_000_000_000)},
	{suffix: "w", factor: big.NewInt(604_800_000_000_000)},
	{suffix: "y", factor: big.NewInt(31_536_000_000_000_000)},
}

var byteUnits = []scaledUnit{
	{suffix: "YiB", factor: powBigInt(1024, 8)},
	{suffix: "ZiB", factor: powBigInt(1024, 7)},
	{suffix: "EiB", factor: powBigInt(1024, 6)},
	{suffix: "PiB", factor: powBigInt(1024, 5)},
	{suffix: "TiB", factor: powBigInt(1024, 4)},
	{suffix: "GiB", factor: powBigInt(1024, 3)},
	{suffix: "MiB", factor: powBigInt(1024, 2)},
	{suffix: "KiB", factor: big.NewInt(1024)},
	{suffix: "YB", factor: powBigInt(1000, 8)},
	{suffix: "ZB", factor: powBigInt(1000, 7)},
	{suffix: "EB", factor: powBigInt(1000, 6)},
	{suffix: "PB", factor: powBigInt(1000, 5)},
	{suffix: "TB", factor: powBigInt(1000, 4)},
	{suffix: "GB", factor: powBigInt(1000, 3)},
	{suffix: "MB", factor: powBigInt(1000, 2)},
	{suffix: "KB", factor: big.NewInt(1000)},
	{suffix: "kB", factor: big.NewInt(1000)},
	{suffix: "B", factor: big.NewInt(1)},
}

func powBigInt(base int64, exponent int64) *big.Int {
	return new(big.Int).Exp(big.NewInt(base), big.NewInt(exponent), nil)
}

type decimalTerm struct {
	coefficient big.Int
	exponent    big.Int
}

type exactValue struct {
	terms []decimalTerm
}

// parseScaledValue parses a sequence such as 1h30m or 1GiB512MiB. A leading
// sign applies to the complete sequence, matching time.Duration and the byte
// parser previously used by Prometheus. Every coefficient accepts the exact
// decimal/scientific grammar used for plain numbers.
func parseScaledValue(value string, units []scaledUnit) (exactValue, bool) {
	var parsed exactValue
	if value == "" {
		return parsed, false
	}

	i := 0
	sign := 1
	if value[i] == '+' || value[i] == '-' {
		if value[i] == '-' {
			sign = -1
		}
		i++
		if i == len(value) {
			return parsed, false
		}
	}

	for i < len(value) {
		coefficient, end, ok := parseExactDecimalPrefix(value, i)
		if !ok || coefficient.sign < 0 || end == i {
			return exactValue{}, false
		}

		unit, ok := matchScaledUnit(value[end:], units)
		if !ok {
			return exactValue{}, false
		}
		i = end + len(unit.suffix)

		if coefficient.sign == 0 {
			continue
		}
		var term decimalTerm
		term.coefficient.SetString(coefficient.coefficient, 10)
		term.coefficient.Mul(&term.coefficient, unit.factor)
		if sign < 0 {
			term.coefficient.Neg(&term.coefficient)
		}
		term.exponent.Set(&coefficient.exponent)
		normalizeDecimalTerm(&term)
		parsed.terms = append(parsed.terms, term)
	}

	return parsed, true
}

func matchScaledUnit(value string, units []scaledUnit) (scaledUnit, bool) {
	for _, unit := range units {
		if strings.HasPrefix(value, unit.suffix) {
			return unit, true
		}
	}
	return scaledUnit{}, false
}

func normalizeDecimalTerm(term *decimalTerm) {
	if term.coefficient.Sign() == 0 {
		term.exponent.SetInt64(0)
		return
	}

	text := term.coefficient.Text(10)
	digits := text
	if digits[0] == '-' {
		digits = digits[1:]
	}
	zeros := len(digits) - len(strings.TrimRight(digits, "0"))
	if zeros == 0 {
		return
	}

	term.coefficient.Quo(&term.coefficient, powBigInt(10, int64(zeros)))
	term.exponent.Add(&term.exponent, new(big.Int).SetUint64(uint64(zeros)))
}

func (v exactValue) cmp(other exactValue) int {
	terms := make([]orderedDecimalTerm, 0, len(v.terms)+len(other.terms))
	for i := range v.terms {
		terms = append(terms, newOrderedDecimalTerm(&v.terms[i], false))
	}
	for i := range other.terms {
		terms = append(terms, newOrderedDecimalTerm(&other.terms[i], true))
	}
	return signOfDecimalSum(terms)
}

type orderedDecimalTerm struct {
	term  decimalTerm
	order big.Int
}

func newOrderedDecimalTerm(term *decimalTerm, negate bool) orderedDecimalTerm {
	var result orderedDecimalTerm
	result.term.coefficient.Set(&term.coefficient)
	if negate {
		result.term.coefficient.Neg(&result.term.coefficient)
	}
	result.term.exponent.Set(&term.exponent)
	result.order.Set(decimalOrder(&result.term.exponent, decimalDigits(&result.term.coefficient)))
	return result
}

// signOfDecimalSum computes the sign of a sparse decimal sum. It combines only
// terms close enough in magnitude to affect one another. This means values such
// as 1e100000000000000000000s can be compared exactly without constructing a
// decimal integer with that many zeroes.
func signOfDecimalSum(terms []orderedDecimalTerm) int {
	if len(terms) == 0 {
		return 0
	}

	sort.Slice(terms, func(i, j int) bool {
		a, b := terms[i], terms[j]
		if result := b.order.Cmp(&a.order); result != 0 {
			return result < 0
		}
		return b.term.exponent.Cmp(&a.term.exponent) < 0
	})

	var coefficient, exponent big.Int
	for i := range terms {
		if coefficient.Sign() == 0 {
			coefficient.Set(&terms[i].term.coefficient)
			exponent.Set(&terms[i].term.exponent)
		} else if !addDecimalTerm(&coefficient, &exponent, &terms[i].term) {
			// A shift too large to represent in memory can only occur when the
			// accumulated term dominates all remaining input-sized terms.
			return coefficient.Sign()
		}

		if i == len(terms)-1 {
			return coefficient.Sign()
		}
		if coefficient.Sign() == 0 {
			continue
		}

		currentOrder := decimalOrder(&exponent, decimalDigits(&coefficient))
		currentLowerBound := new(big.Int).Sub(currentOrder, big.NewInt(1))
		remainingUpperBound := new(big.Int).Set(&terms[i+1].order)
		remainingUpperBound.Add(remainingUpperBound, new(big.Int).SetUint64(uint64(ceilLog10(len(terms)-i-1))))
		if currentLowerBound.Cmp(remainingUpperBound) >= 0 {
			return coefficient.Sign()
		}
	}
	return coefficient.Sign()
}

func addDecimalTerm(coefficient, exponent *big.Int, term *decimalTerm) bool {
	switch exponent.Cmp(&term.exponent) {
	case 0:
		coefficient.Add(coefficient, &term.coefficient)
	case 1:
		shift := new(big.Int).Sub(exponent, &term.exponent)
		multiplier, ok := decimalShift(shift)
		if !ok {
			return false
		}
		coefficient.Mul(coefficient, multiplier)
		coefficient.Add(coefficient, &term.coefficient)
		exponent.Set(&term.exponent)
	case -1:
		shift := new(big.Int).Sub(&term.exponent, exponent)
		multiplier, ok := decimalShift(shift)
		if !ok {
			return false
		}
		shiftedTerm := new(big.Int).Mul(&term.coefficient, multiplier)
		coefficient.Add(coefficient, shiftedTerm)
	}

	accumulator := decimalTerm{coefficient: *coefficient, exponent: *exponent}
	normalizeDecimalTerm(&accumulator)
	coefficient.Set(&accumulator.coefficient)
	exponent.Set(&accumulator.exponent)
	return true
}

func decimalShift(shift *big.Int) (*big.Int, bool) {
	if !shift.IsUint64() {
		return nil, false
	}
	n := shift.Uint64()
	maxInt := uint64(^uint(0) >> 1)
	if n > maxInt {
		return nil, false
	}
	return new(big.Int).Exp(big.NewInt(10), new(big.Int).SetUint64(n), nil), true
}

func decimalDigits(value *big.Int) int {
	if value.Sign() < 0 {
		return len(value.Text(10)) - 1
	}
	return len(value.Text(10))
}

func ceilLog10(value int) int {
	if value <= 1 {
		return 0
	}
	power, result := 1, 0
	for power < value {
		if power > int(^uint(0)>>1)/10 {
			return result + 1
		}
		power *= 10
		result++
	}
	return result
}

type semanticVersion struct {
	core       [3]string
	prerelease []string
}

func parseSemanticVersion(value string) (semanticVersion, bool) {
	var version semanticVersion
	if strings.HasPrefix(value, "v") {
		value = value[1:]
	}
	if value == "" {
		return version, false
	}

	withoutBuild := value
	if plus := strings.IndexByte(withoutBuild, '+'); plus >= 0 {
		build := withoutBuild[plus+1:]
		withoutBuild = withoutBuild[:plus]
		if !validSemverIdentifiers(build, false) {
			return version, false
		}
	}

	core := withoutBuild
	if dash := strings.IndexByte(core, '-'); dash >= 0 {
		prerelease := core[dash+1:]
		core = core[:dash]
		if !validSemverIdentifiers(prerelease, true) {
			return version, false
		}
		version.prerelease = strings.Split(prerelease, ".")
	}

	parts := strings.Split(core, ".")
	if len(parts) != len(version.core) {
		return semanticVersion{}, false
	}
	for i, part := range parts {
		if !validSemverNumber(part) {
			return semanticVersion{}, false
		}
		version.core[i] = part
	}
	return version, true
}

func validSemverNumber(value string) bool {
	if value == "" || len(value) > 1 && value[0] == '0' {
		return false
	}
	for i := range value {
		if !isASCIIDigit(value[i]) {
			return false
		}
	}
	return true
}

func validSemverIdentifiers(value string, prerelease bool) bool {
	if value == "" {
		return false
	}
	for _, identifier := range strings.Split(value, ".") {
		if identifier == "" {
			return false
		}
		numeric := true
		for i := range identifier {
			c := identifier[i]
			if !isASCIIDigit(c) {
				numeric = false
			}
			if !isASCIIDigit(c) && !(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') && c != '-' {
				return false
			}
		}
		if prerelease && numeric && len(identifier) > 1 && identifier[0] == '0' {
			return false
		}
	}
	return true
}

func (v semanticVersion) cmp(other semanticVersion) int {
	for i := range v.core {
		if result := compareUnsignedDecimalStrings(v.core[i], other.core[i]); result != 0 {
			return result
		}
	}

	if len(v.prerelease) == 0 || len(other.prerelease) == 0 {
		switch {
		case len(v.prerelease) == 0 && len(other.prerelease) == 0:
			return 0
		case len(v.prerelease) == 0:
			return 1
		default:
			return -1
		}
	}

	common := minInt(len(v.prerelease), len(other.prerelease))
	for i := 0; i < common; i++ {
		a, b := v.prerelease[i], other.prerelease[i]
		aNumeric, bNumeric := allASCIIDigits(a), allASCIIDigits(b)
		switch {
		case aNumeric && bNumeric:
			if result := compareUnsignedDecimalStrings(a, b); result != 0 {
				return result
			}
		case aNumeric:
			return -1
		case bNumeric:
			return 1
		default:
			if result := strings.Compare(a, b); result != 0 {
				return result
			}
		}
	}
	return compareValues(len(v.prerelease), len(other.prerelease))
}

func compareUnsignedDecimalStrings(a, b string) int {
	if len(a) != len(b) {
		return compareValues(len(a), len(b))
	}
	return strings.Compare(a, b)
}

func allASCIIDigits(value string) bool {
	if value == "" {
		return false
	}
	for i := range value {
		if !isASCIIDigit(value[i]) {
			return false
		}
	}
	return true
}

func compareAddresses(a, b netip.Addr) int {
	if a.Is4() != b.Is4() {
		if a.Is4() {
			return -1
		}
		return 1
	}

	var result int
	if a.Is4() {
		aa, bb := a.As4(), b.As4()
		result = bytes.Compare(aa[:], bb[:])
	} else {
		aa, bb := a.As16(), b.As16()
		result = bytes.Compare(aa[:], bb[:])
	}
	if result != 0 {
		return result
	}
	return strings.Compare(a.Zone(), b.Zone())
}

func comparePrefixes(a, b netip.Prefix) int {
	if result := compareAddresses(a.Addr(), b.Addr()); result != 0 {
		return result
	}
	return compareValues(a.Bits(), b.Bits())
}

// compareNatural compares digit runs by their arbitrary-size integer value and
// all other bytes lexically. Naturally equivalent spellings receive a lexical
// tie-break, making the result a total order (unlike facette/natsort, which can
// report both a < b and b < a for equivalent digit runs).
func compareNatural(a, b string) int {
	ai, bi := 0, 0
	for ai < len(a) && bi < len(b) {
		if isASCIIDigit(a[ai]) && isASCIIDigit(b[bi]) {
			aEnd, bEnd := ai, bi
			for aEnd < len(a) && isASCIIDigit(a[aEnd]) {
				aEnd++
			}
			for bEnd < len(b) && isASCIIDigit(b[bEnd]) {
				bEnd++
			}

			aSignificant, bSignificant := ai, bi
			for aSignificant < aEnd && a[aSignificant] == '0' {
				aSignificant++
			}
			for bSignificant < bEnd && b[bSignificant] == '0' {
				bSignificant++
			}
			if aDigits, bDigits := aEnd-aSignificant, bEnd-bSignificant; aDigits != bDigits {
				return compareValues(aDigits, bDigits)
			}
			if result := strings.Compare(a[aSignificant:aEnd], b[bSignificant:bEnd]); result != 0 {
				return result
			}
			ai, bi = aEnd, bEnd
			continue
		}

		if a[ai] != b[bi] {
			return compareValues(a[ai], b[bi])
		}
		ai++
		bi++
	}
	if ai != len(a) || bi != len(b) {
		return compareValues(len(a)-ai, len(b)-bi)
	}
	return strings.Compare(a, b)
}

func isASCIIDigit(c byte) bool {
	return c >= '0' && c <= '9'
}

// compareValues provides the ordered three-way comparison that cmp.Compare
// offers in newer Go releases.
type orderedValue interface {
	~int | ~int8 | ~int16 | ~int32 | ~int64 |
		~uint | ~uint8 | ~uint16 | ~uint32 | ~uint64 | ~uintptr |
		~float32 | ~float64 | ~string
}

func compareValues[T orderedValue](a, b T) int {
	switch {
	case a < b:
		return -1
	case a > b:
		return 1
	default:
		return 0
	}
}

func compareTimestamps(a, b time.Time) int {
	switch {
	case a.Before(b):
		return -1
	case a.After(b):
		return 1
	default:
		return 0
	}
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// CompareLabelValues compares two label values using the multi-domain typed
// ordering, falling back to natural comparison within a class.
func CompareLabelValues(a, b string) int { return compareLabelValues(a, b) }
