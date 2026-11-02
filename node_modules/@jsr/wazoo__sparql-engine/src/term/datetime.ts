/**
 * datetime.ts implements the xsd:dateTime value surface the SPARQL date/time
 * functions (YEAR, MONTH, DAY, HOURS, MINUTES, SECONDS, TIMEZONE) need:
 * strict lexical parsing and the xsd:dayTimeDuration lexical form for
 * timezone offsets.
 */

/**
 * DateTimeParts is the parsed component view of an xsd:dateTime literal.
 */
export interface DateTimeParts {
  /** year is the (possibly negative) calendar year. */
  year: number;

  /** month is 1-12. */
  month: number;

  /** day is 1-31. */
  day: number;

  /** hours is 0-23. */
  hours: number;

  /** minutes is 0-59. */
  minutes: number;

  /** seconds includes any fractional part (13 or 13.815). */
  seconds: number;

  /** hasTimezone is false when the lexical form has no timezone. */
  hasTimezone: boolean;

  /** timezoneMinutes is the signed UTC offset in minutes (0 for Z). */
  timezoneMinutes: number;
}

const DATE_TIME_PATTERN =
  /^(-?\d{4,})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/;

/**
 * parseDateTime parses an xsd:dateTime lexical form into its components, or
 * null when the form is malformed or out of range.
 */
export function parseDateTime(lexical: string): DateTimeParts | null {
  const match = DATE_TIME_PATTERN.exec(lexical);
  if (match === null) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hours = Number(match[4]);
  const minutes = Number(match[5]);
  const seconds = Number(match[6]);
  if (
    month < 1 || month > 12 || day < 1 || day > 31 ||
    hours > 23 || minutes > 59 || seconds > 60
  ) {
    return null;
  }
  let hasTimezone = false;
  let timezoneMinutes = 0;
  const timezone = match[8];
  if (timezone !== undefined) {
    hasTimezone = true;
    if (timezone !== "Z") {
      const sign = timezone[0] === "-" ? -1 : 1;
      const tzHours = Number(timezone.slice(1, 3));
      const tzMinutes = Number(timezone.slice(4, 6));
      if (tzHours > 23 || tzMinutes > 59) {
        return null;
      }
      timezoneMinutes = sign * (tzHours * 60 + tzMinutes);
    }
  }
  return {
    year,
    month,
    day,
    hours,
    minutes,
    seconds: match[7] !== undefined ? Number(match[6] + match[7]) : seconds,
    hasTimezone,
    timezoneMinutes,
  };
}

/**
 * timezoneDurationLexical renders a signed UTC offset in minutes as the
 * canonical xsd:dayTimeDuration lexical form: "PT0S" for zero, "-PT5H" for
 * -05:00, "PT5H30M" for +05:30.
 */
export function timezoneDurationLexical(offsetMinutes: number): string {
  if (offsetMinutes === 0) {
    return "PT0S";
  }
  const sign = offsetMinutes < 0 ? "-" : "";
  const total = Math.abs(offsetMinutes);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  let result = `${sign}PT`;
  if (hours > 0) {
    result += `${hours}H`;
  }
  if (minutes > 0) {
    result += `${minutes}M`;
  }
  if (hours === 0 && minutes === 0) {
    result += "0S";
  }
  return result;
}
