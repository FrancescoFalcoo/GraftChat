/**
 * DOM selection <-> offsets in the raw message string.
 *
 * The message renderer guarantees `root.textContent === content`, so an offset in the
 * concatenated text nodes of `root` is a UTF-16 offset in `content`. The server wants
 * Unicode code points (Python string indices): the conversion happens here.
 */

export interface AnchorSelection {
  /** Code point offsets into the raw content, end exclusive. */
  start: number;
  end: number;
  /** Exactly `content[start:end]` as Python sees it. */
  quote: string;
}

const ROOT_SELECTOR = "[data-anchor-root]";

export function utf16ToCodePoints(content: string, utf16: number): number {
  return Array.from(content.slice(0, utf16)).length;
}

export function codePointsToUtf16(content: string, codePoints: number): number {
  let cp = 0;
  let i = 0;
  while (i < content.length && cp < codePoints) {
    const code = content.codePointAt(i);
    i += code !== undefined && code > 0xffff ? 2 : 1;
    cp++;
  }
  return i;
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

function isLowSurrogate(code: number): boolean {
  return code >= 0xdc00 && code <= 0xdfff;
}

/** True when `i` falls between the two halves of a surrogate pair. */
function splitsPair(content: string, i: number): boolean {
  return (
    i > 0 &&
    i < content.length &&
    isHighSurrogate(content.charCodeAt(i - 1)) &&
    isLowSurrogate(content.charCodeAt(i))
  );
}

/**
 * UTF-16 offset, in the concatenated text of `root`, of the DOM boundary point
 * (`node`, `offset`). Returns null when the point is outside `root`.
 */
export function boundaryToTextOffset(root: Node, node: Node, offset: number): number | null {
  if (node !== root && !root.contains(node)) return null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let total = 0;

  if (node.nodeType === Node.TEXT_NODE) {
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
      if (t === node) return total + Math.min(offset, (t as Text).data.length);
      total += (t as Text).data.length;
    }
    return null;
  }

  // Element boundary: the point sits just before child number `offset`, or at the very
  // end of `node` when there is no such child.
  const child = node.childNodes[offset] ?? null;
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (child) {
      if (t === child || child.contains(t)) break;
      if (child.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING) break;
    } else if (
      !node.contains(t) &&
      node.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING
    ) {
      break;
    }
    total += (t as Text).data.length;
  }
  return total;
}

/**
 * Converts a Range inside `root` (the content element of one message) into trimmed
 * code point offsets. Returns null if the range is not inside `root`, if the rendered
 * text does not match `content`, or if nothing is left after trimming whitespace.
 */
export function rangeToSelection(
  root: Element,
  range: Range,
  content: string,
): AnchorSelection | null {
  if (root.textContent !== content) return null;
  const a = boundaryToTextOffset(root, range.startContainer, range.startOffset);
  const b = boundaryToTextOffset(root, range.endContainer, range.endOffset);
  if (a === null || b === null) return null;

  let start = Math.min(a, b);
  let end = Math.max(a, b);
  if (splitsPair(content, start)) start--;
  if (splitsPair(content, end)) end++;
  while (start < end && /\s/.test(content[start])) start++;
  while (end > start && /\s/.test(content[end - 1])) end--;
  if (start >= end) return null;

  const quote = content.slice(start, end);
  const cpStart = utf16ToCodePoints(content, start);
  return { start: cpStart, end: cpStart + Array.from(quote).length, quote };
}

/** Inverse of rangeToSelection: a DOM Range covering content[start:end] (code points). */
export function offsetsToRange(
  root: Element,
  content: string,
  start: number,
  end: number,
): Range | null {
  if (root.textContent !== content) return null;
  const from = codePointsToUtf16(content, start);
  const to = codePointsToUtf16(content, end);
  if (from >= to) return null;

  const range = document.createRange();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let total = 0;
  let startSet = false;
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    const len = (t as Text).data.length;
    // Start goes at the beginning of a node rather than at the end of the previous one;
    // end goes at the end of a node rather than at the beginning of the next one.
    if (!startSet && from < total + len) {
      range.setStart(t, from - total);
      startSet = true;
    }
    if (startSet && to <= total + len) {
      range.setEnd(t, to - total);
      return range;
    }
    total += len;
  }
  return null;
}

function closestRoot(node: Node): HTMLElement | null {
  const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  return el ? el.closest<HTMLElement>(ROOT_SELECTOR) : null;
}

function isBlank(doc: Document, sn: Node, so: number, en: Node, eo: number): boolean {
  const r = doc.createRange();
  r.setStart(sn, so);
  r.setEnd(en, eo);
  return r.toString().trim() === "";
}

/**
 * Finds the single selectable message (an element with `data-anchor-root`, inside
 * `scope`) that contains the whole range. A range that only spills over the message
 * edge without taking any text with it (what a triple click produces) is clipped to
 * the message. Anything else spanning outside one message is rejected.
 */
export function findAnchorRoot(
  range: Range,
  scope: Element,
): { root: HTMLElement; range: Range } | null {
  if (range.collapsed) return null;
  const doc = scope.ownerDocument;
  const startRoot = closestRoot(range.startContainer);
  const endRoot = closestRoot(range.endContainer);
  const root = startRoot ?? endRoot;
  if (!root || !scope.contains(root)) return null;
  if (startRoot && endRoot && startRoot !== endRoot) return null;

  const clipped = range.cloneRange();
  if (!endRoot) {
    const last = root.childNodes.length;
    // A triple click on the last line of a message ends the range at offset 0 of the
    // next block on the page (chips, buttons, the composer...): the range takes no
    // character from it, even if UI text lies in between, so clip it to the message.
    const atNextBlockStart =
      range.endOffset === 0 &&
      root.compareDocumentPosition(range.endContainer) & Node.DOCUMENT_POSITION_FOLLOWING;
    if (!atNextBlockStart && !isBlank(doc, root, last, range.endContainer, range.endOffset)) {
      return null;
    }
    clipped.setEnd(root, last);
  }
  if (!startRoot) {
    if (!isBlank(doc, range.startContainer, range.startOffset, root, 0)) return null;
    clipped.setStart(root, 0);
  }
  return { root, range: clipped };
}

/** Content element of a selectable message, looked up by message id. */
export function findRootByMessageId(scope: Element, messageId: number): HTMLElement | null {
  return scope.querySelector<HTMLElement>(`${ROOT_SELECTOR}[data-msg-id="${messageId}"]`);
}
