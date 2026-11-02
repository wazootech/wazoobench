/**
 * SparqlSyntaxError is the typed, position-aware error thrown for SPARQL
 * syntax failures, surfaced through both `Parser.parse` and
 * `WazooSparqlEngine.execute`.
 *
 * The generated jison parser (parser.ts) throws a plain `Error` whose message
 * embeds a caret line and whose `.hash` carries `{ text, token, line, loc,
 * expected }`. `toSparqlSyntaxError` maps that into this structured error:
 * 1-based line and column, the offending source line, the matched text, the
 * token symbol, the expected-token set, and the raw jison message. Lexer
 * failures ("Unrecognized text") become `kind: "lexical"` errors with no
 * token or expected set.
 *
 * Column precision: jison's own `loc` fields are unreliable in this
 * generated parser and its caret line truncates past 20 characters, so the
 * column is computed by locating the matched token text on the error line —
 * exact for the common cases (a token that appears once on its line, or the
 * error at end of input), with the last occurrence preferred when a
 * delimiter repeats (e.g. a stray closing brace at the end of a query).
 */

/** SparqlSyntaxErrorKind distinguishes lexer from parser failures. */
export type SparqlSyntaxErrorKind = "parse" | "lexical";

/** SparqlSyntaxErrorDetails is the structured payload of a syntax error. */
export interface SparqlSyntaxErrorDetails {
  kind: SparqlSyntaxErrorKind;
  /** 1-based line of the error. */
  line: number;
  /** 1-based column of the error within its line. */
  column: number;
  /** The offending source line (no trailing newline). */
  excerpt: string;
  /** The text matched at the error ("" for end-of-input / lexical errors). */
  text: string;
  /** The offending token symbol (parse errors); null for lexical errors. */
  token: string | null;
  /** The token set the parser was expecting (parse errors; may be empty). */
  expected: string[];
  /** The generated jison error message. */
  rawMessage: string;
}

/** SparqlSyntaxError is a line/column-positioned SPARQL syntax error. */
export class SparqlSyntaxError extends Error {
  override readonly name = "SparqlSyntaxError";

  readonly kind: SparqlSyntaxErrorKind;
  readonly line: number;
  readonly column: number;
  readonly excerpt: string;
  readonly text: string;
  readonly token: string | null;
  readonly expected: string[];
  readonly rawMessage: string;

  public constructor(details: SparqlSyntaxErrorDetails) {
    super(formatMessage(details));
    this.kind = details.kind;
    this.line = details.line;
    this.column = details.column;
    this.excerpt = details.excerpt;
    this.text = details.text;
    this.token = details.token;
    this.expected = details.expected;
    this.rawMessage = details.rawMessage;
  }
}

/** formatMessage renders a human-readable "line L, column C" message. */
function formatMessage(details: SparqlSyntaxErrorDetails): string {
  const where =
    `Syntax error at line ${details.line}, column ${details.column}`;
  const detail = details.kind === "lexical"
    ? "unrecognized text"
    : `unexpected '${details.token ?? details.text}'; expecting ` +
      (details.expected.length > 0
        ? details.expected.join(", ")
        : "end of input");
  const caret = " ".repeat(
    Math.max(0, Math.min(details.column - 1, details.excerpt.length)),
  ) + "^";
  return `${where}: ${detail}\n\n${details.excerpt}\n${caret}`;
}

/** JisonErrorHash is the non-standard `.hash` the generated parser attaches. */
interface JisonErrorHash {
  text?: unknown;
  token?: unknown;
  line?: unknown;
  expected?: unknown;
}

/**
 * toSparqlSyntaxError maps a generated jison parse/lex error into a
 * SparqlSyntaxError, or returns null when the error is not a syntax failure
 * (e.g. sparqljs validation errors like unresolvable relative IRIs pass
 * through unchanged).
 */
export function toSparqlSyntaxError(
  input: string,
  error: unknown,
): SparqlSyntaxError | null {
  if (!(error instanceof Error)) {
    return null;
  }
  const message = error.message;
  const parseMatch = /^Parse error on line (\d+)/.exec(message);
  const lexMatch = /^Lexical error on line (\d+)/.exec(message);
  if (!parseMatch && !lexMatch) {
    return null;
  }
  const hash = (error as Error & { hash?: JisonErrorHash }).hash ?? {};
  const hashLine = typeof hash.line === "number" ? hash.line : undefined;
  const line = hashLine !== undefined
    ? hashLine + 1
    : Number.parseInt(parseMatch?.[1] ?? lexMatch?.[1] ?? "1", 10);
  const text = typeof hash.text === "string" ? hash.text : "";
  const token = typeof hash.token === "string" ? hash.token : null;
  const expected = Array.isArray(hash.expected)
    ? hash.expected.map(String)
    : [];
  const excerpt = input.split(/\r?\n/)[line - 1] ?? "";
  let column: number;
  if (text === "") {
    column = excerpt.length + 1;
  } else {
    let index = excerpt.lastIndexOf(text);
    if (index < 0) {
      index = excerpt.indexOf(text);
    }
    column = index < 0 ? excerpt.length + 1 : index + 1;
  }
  return new SparqlSyntaxError({
    kind: lexMatch ? "lexical" : "parse",
    line,
    column,
    excerpt,
    text,
    token,
    expected,
    rawMessage: message,
  });
}
