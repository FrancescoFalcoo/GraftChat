/**
 * Character-preserving markdown tokenizer.
 *
 * Invariant: concatenating the text of every token, in order, gives back the source
 * string exactly. Nothing is dropped, duplicated or reordered, so offsets in the
 * rendered text are offsets in the raw message (see selection.ts).
 *
 * The parser is deliberately conservative: anything doubtful stays plain text.
 */

export type Inline =
  | { t: "text"; s: string }
  /** Markup characters hidden by CSS (still in the DOM, still counted). */
  | { t: "mk"; s: string }
  /** Markup characters that stay visible (list bullets, "> "). */
  | { t: "marker"; s: string }
  | { t: "strong" | "em" | "code"; c: Inline[] };

export type LineKind = "p" | "blank" | "h" | "li" | "bq" | "fence" | "code";

export interface Line {
  kind: LineKind;
  /** Heading level (1-6) for "h", 0 otherwise. */
  level: number;
  /** For "fence" lines: whether the line opens or closes the block. */
  fence: "open" | "close" | null;
  /** Tokens of the line, end-of-line characters included as the last text token. */
  parts: Inline[];
}

const text = (s: string): Inline => ({ t: "text", s });
const mk = (s: string): Inline => ({ t: "mk", s });
const marker = (s: string): Inline => ({ t: "marker", s });

const WORD = /[\p{L}\p{N}]/u;
const isWord = (ch: string | undefined): boolean => ch !== undefined && WORD.test(ch);
const isSpace = (ch: string | undefined): boolean => ch === undefined || /\s/.test(ch);

const FENCE_OPEN = /^ {0,3}```[^`]*$/;
const FENCE_CLOSE = /^ {0,3}```+\s*$/;
const HEADING = /^(#{1,6})([ \t]+)(\S[\s\S]*)$/;
const QUOTE = /^ {0,3}> ?/;
const LIST = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+)(?=\S)/;
const ESCAPABLE = "\\`*_";

/** Splits into lines; each keeps its own terminator ("\n", "\r\n" or "" for the last). */
export function splitLines(content: string): { body: string; eol: string }[] {
  const out: { body: string; eol: string }[] = [];
  let i = 0;
  while (i < content.length) {
    const nl = content.indexOf("\n", i);
    if (nl === -1) {
      out.push({ body: content.slice(i), eol: "" });
      break;
    }
    const crlf = nl > i && content[nl - 1] === "\r";
    out.push({ body: content.slice(i, crlf ? nl - 1 : nl), eol: crlf ? "\r\n" : "\n" });
    i = nl + 1;
  }
  return out;
}

function runLength(s: string, i: number): number {
  const ch = s[i];
  let n = 1;
  while (s[i + n] === ch) n++;
  return n;
}

/** Index of the next run of exactly `n` backticks at or after `from`, or -1. */
function findBacktickCloser(s: string, from: number, n: number): number {
  let i = from;
  while (i < s.length) {
    if (s[i] === "`") {
      const len = runLength(s, i);
      if (len === n) return i;
      i += len;
    } else {
      i++;
    }
  }
  return -1;
}

/**
 * Index of the run of exactly `n` `ch` that closes an emphasis opened just before
 * `from`, or -1. Code spans and escaped characters are skipped.
 */
function findEmphasisCloser(s: string, from: number, ch: string, n: number): number {
  let i = from;
  while (i < s.length) {
    const c = s[i];
    if (c === "\\") {
      i += 2;
    } else if (c === "`") {
      const len = runLength(s, i);
      const close = findBacktickCloser(s, i + len, len);
      i = close === -1 ? i + len : close + len;
    } else if (c === ch) {
      const len = runLength(s, i);
      if (len === n && i > from && !isSpace(s[i - 1]) && !isWord(s[i + len])) return i;
      i += len;
    } else {
      i++;
    }
  }
  return -1;
}

export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  // Closer searches that already failed: a later search for the same marker would
  // fail too, so skipping it keeps pathological lines linear.
  const failed = new Set<string>();
  let buf = "";
  const flush = (): void => {
    if (buf) {
      out.push(text(buf));
      buf = "";
    }
  };

  let i = 0;
  while (i < s.length) {
    const c = s[i];

    if (c === "\\" && i + 1 < s.length && ESCAPABLE.includes(s[i + 1])) {
      buf += s.slice(i, i + 2);
      i += 2;
      continue;
    }

    if (c === "`") {
      const n = runLength(s, i);
      const key = "`" + n;
      const close = failed.has(key) ? -1 : findBacktickCloser(s, i + n, n);
      if (close !== -1) {
        flush();
        out.push({
          t: "code",
          c: [mk(s.slice(i, i + n)), text(s.slice(i + n, close)), mk(s.slice(close, close + n))],
        });
        i = close + n;
        continue;
      }
      failed.add(key);
      buf += s.slice(i, i + n);
      i += n;
      continue;
    }

    if (c === "*" || c === "_") {
      const n = runLength(s, i);
      const key = c + n;
      const canOpen =
        n <= (c === "*" ? 3 : 1) && !isWord(s[i - 1]) && !isSpace(s[i + n]) && !failed.has(key);
      if (canOpen) {
        const close = findEmphasisCloser(s, i + n, c, n);
        if (close !== -1) {
          flush();
          const open = mk(s.slice(i, i + n));
          const end = mk(s.slice(close, close + n));
          const inner = parseInline(s.slice(i + n, close));
          if (n === 1) out.push({ t: "em", c: [open, ...inner, end] });
          else if (n === 2) out.push({ t: "strong", c: [open, ...inner, end] });
          else out.push({ t: "strong", c: [open, { t: "em", c: inner }, end] });
          i = close + n;
          continue;
        }
        failed.add(key);
      }
      buf += s.slice(i, i + n);
      i += n;
      continue;
    }

    buf += c;
    i++;
  }
  flush();
  return out;
}

export function parseMarkdown(content: string): Line[] {
  const lines: Line[] = [];
  let inFence = false;

  for (const { body, eol } of splitLines(content)) {
    let kind: LineKind = "p";
    let level = 0;
    let fence: Line["fence"] = null;
    let parts: Inline[];
    let m: RegExpExecArray | null;

    if (inFence) {
      if (FENCE_CLOSE.test(body)) {
        kind = "fence";
        fence = "close";
        inFence = false;
      } else {
        kind = "code";
      }
      parts = body ? [text(body)] : [];
    } else if (FENCE_OPEN.test(body)) {
      kind = "fence";
      fence = "open";
      inFence = true;
      parts = [text(body)];
    } else if (body.trim() === "") {
      kind = "blank";
      parts = body ? [text(body)] : [];
    } else if ((m = HEADING.exec(body))) {
      kind = "h";
      level = m[1].length;
      parts = [mk(m[1] + m[2]), ...parseInline(m[3])];
    } else if ((m = QUOTE.exec(body))) {
      kind = "bq";
      parts = [marker(m[0]), ...parseInline(body.slice(m[0].length))];
    } else if ((m = LIST.exec(body))) {
      kind = "li";
      parts = [];
      if (m[1]) parts.push(text(m[1]));
      parts.push(marker(m[2] + m[3]), ...parseInline(body.slice(m[0].length)));
    } else {
      parts = parseInline(body);
    }

    if (eol) parts.push(text(eol));
    lines.push({ kind, level, fence, parts });
  }
  return lines;
}

export function inlineText(parts: Inline[]): string {
  let s = "";
  for (const p of parts) s += "c" in p ? inlineText(p.c) : p.s;
  return s;
}

/** The source string rebuilt from the tokens (always equal to the parser's input). */
export function linesText(lines: Line[]): string {
  return lines.map((l) => inlineText(l.parts)).join("");
}
