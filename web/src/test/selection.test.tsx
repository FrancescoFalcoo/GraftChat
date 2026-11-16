import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MessageContent } from "../components/MessageContent";
import {
  boundaryToTextOffset,
  codePointsToUtf16,
  findAnchorRoot,
  offsetsToRange,
  rangeToSelection,
  utf16ToCodePoints,
} from "../selection";

afterEach(cleanup);

/** What Python's content[start:end] returns. */
function cpSlice(content: string, start: number, end: number): string {
  return Array.from(content).slice(start, end).join("");
}

function renderMd(content: string, selectable = true, id = 1): HTMLElement {
  const { container } = render(
    <MessageContent content={content} messageId={id} selectable={selectable} />,
  );
  return container.querySelector<HTMLElement>(".md")!;
}

/** Text node of `root` containing `needle`, and the offset of `needle` in it. */
function locate(root: Element, needle: string): [Text, number] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    const i = (t as Text).data.indexOf(needle);
    if (i !== -1) return [t as Text, i];
  }
  throw new Error(`text not found: ${needle}`);
}

function rangeBetween(root: Element, from: string, to: string): Range {
  const [sn, so] = locate(root, from);
  const [en, eo] = locate(root, to);
  const r = document.createRange();
  r.setStart(sn, so);
  r.setEnd(en, eo + to.length);
  return r;
}

describe("code point conversion", () => {
  it("converts both ways around astral characters", () => {
    const s = "a\u{1F600}b\u{20000}c";
    expect(utf16ToCodePoints(s, 0)).toBe(0);
    expect(utf16ToCodePoints(s, 1)).toBe(1);
    expect(utf16ToCodePoints(s, 3)).toBe(2);
    expect(utf16ToCodePoints(s, 4)).toBe(3);
    expect(utf16ToCodePoints(s, 6)).toBe(4);
    expect(utf16ToCodePoints(s, 7)).toBe(5);
    for (let cp = 0; cp <= 5; cp++) {
      expect(utf16ToCodePoints(s, codePointsToUtf16(s, cp))).toBe(cp);
    }
    expect(codePointsToUtf16(s, 99)).toBe(s.length);
  });
});

describe("rangeToSelection", () => {
  it("maps a selection inside one text node", () => {
    const content = "The quick brown fox";
    const root = renderMd(content);
    const sel = rangeToSelection(root, rangeBetween(root, "quick", "brown"), content);
    expect(sel).toEqual({ start: 4, end: 15, quote: "quick brown" });
    expect(cpSlice(content, sel!.start, sel!.end)).toBe(sel!.quote);
  });

  it("counts hidden markers and spans several lines and elements", () => {
    const content = "# Title\n\nSome **bold** and `code`\n- item *one*\n- item two\n";
    const root = renderMd(content);
    const sel = rangeToSelection(root, rangeBetween(root, "bold", "one"), content)!;
    expect(sel.quote).toBe("bold** and `code`\n- item *one");
    expect(cpSlice(content, sel.start, sel.end)).toBe(sel.quote);
    expect(sel.start).toBe(content.indexOf("bold"));
  });

  it("uses code points when emoji come before the selection", () => {
    const content = "\u{1F600}\u{1F680} launch \u{1F468}‍\u{1F469} **now** please";
    const root = renderMd(content);
    const sel = rangeToSelection(root, rangeBetween(root, "now", "please"), content)!;
    const utf16Start = content.indexOf("now");
    expect(sel.quote).toBe("now** please");
    expect(sel.start).toBe(utf16Start - 4); // four astral characters before it
    expect(sel.start).not.toBe(utf16Start);
    expect(cpSlice(content, sel.start, sel.end)).toBe(sel.quote);
  });

  it("counts emoji inside the selection once", () => {
    const content = "go \u{1F600}\u{1F600} stop";
    const root = renderMd(content);
    const sel = rangeToSelection(root, rangeBetween(root, "go", "stop"), content)!;
    expect(sel).toEqual({ start: 0, end: 10, quote: content });
    expect(cpSlice(content, 0, 10)).toBe(content);
  });

  it("trims leading and trailing whitespace, newlines included", () => {
    const content = "one\n\n  two three  \n\nfour";
    const root = renderMd(content);
    const r = document.createRange();
    const [sn, so] = locate(root, "one");
    const [en] = locate(root, "four");
    r.setStart(sn, so + 3); // right after "one", before the newlines
    r.setEnd(en, 0); // right before "four"
    const sel = rangeToSelection(root, r, content)!;
    expect(sel.quote).toBe("two three");
    expect(cpSlice(content, sel.start, sel.end)).toBe("two three");
  });

  it("rejects whitespace-only and collapsed selections", () => {
    const content = "a  \n\n  b";
    const root = renderMd(content);
    const [an] = locate(root, "a");
    const [bn, bo] = locate(root, "b");
    const r = document.createRange();
    r.setStart(an, 1);
    r.setEnd(bn, bo);
    expect(rangeToSelection(root, r, content)).toBeNull();
    r.collapse(true);
    expect(rangeToSelection(root, r, content)).toBeNull();
  });

  it("handles boundaries given as element + child index", () => {
    const content = "first\nsecond **b**\nthird";
    const root = renderMd(content);
    const lines = root.querySelectorAll(".ln");

    const whole = document.createRange();
    whole.setStart(root, 0);
    whole.setEnd(root, root.childNodes.length);
    expect(rangeToSelection(root, whole, content)!.quote).toBe(content);

    const middle = document.createRange();
    middle.setStart(root, 1); // before the second line
    middle.setEnd(root, 2); // before the third line
    expect(rangeToSelection(root, middle, content)).toEqual({
      start: 6,
      end: 18,
      quote: "second **b**",
    });

    const inner = document.createRange();
    inner.setStart(lines[1], 1); // before <strong>
    inner.setEnd(lines[2], 0); // start of the third line (triple-click shape)
    expect(rangeToSelection(root, inner, content)!.quote).toBe("**b**");

    const strong = root.querySelector("strong")!;
    const deep = document.createRange();
    deep.setStart(strong, 1); // after the opening .mk
    deep.setEnd(strong, 2); // before the closing .mk
    expect(rangeToSelection(root, deep, content)).toEqual({ start: 15, end: 16, quote: "b" });
  });

  it("returns null for a range outside the root", () => {
    const content = "inside";
    const root = renderMd(content);
    const other = document.createElement("p");
    other.textContent = "outside";
    document.body.appendChild(other);
    const r = document.createRange();
    r.selectNodeContents(other);
    expect(rangeToSelection(root, r, content)).toBeNull();
    expect(boundaryToTextOffset(root, other, 0)).toBeNull();
    other.remove();
  });

  it("returns null when the rendered text is not the given content", () => {
    const root = renderMd("abc");
    const r = document.createRange();
    r.selectNodeContents(root);
    expect(rangeToSelection(root, r, "abd")).toBeNull();
  });

  it("never splits a surrogate pair", () => {
    const content = "a\u{1F600}b";
    const root = renderMd(content);
    const [node] = locate(root, "a");
    const r = document.createRange();
    r.setStart(node, 2); // between the two halves of the emoji
    r.setEnd(node, 4);
    const sel = rangeToSelection(root, r, content)!;
    expect(sel).toEqual({ start: 1, end: 3, quote: "\u{1F600}b" });
  });
});

describe("offsetsToRange (inverse)", () => {
  const SAMPLES = [
    "plain text only",
    "# H \u{1F600}\n\n**bo\u{1F680}ld** _it_ `c`\r\n- li é\n> q\n```\ncode\n```\nend",
    "\u{1F468}‍\u{1F469}‍\u{1F467} family *and* \u{20000}\n\n\ntail",
  ];

  it.each(SAMPLES)("round-trips every code point range of %j", (content) => {
    const root = renderMd(content);
    const cps = Array.from(content);
    for (let s = 0; s < cps.length; s++) {
      for (let e = s + 1; e <= cps.length; e++) {
        const expected = cps.slice(s, e).join("");
        const range = offsetsToRange(root, content, s, e);
        expect(range).not.toBeNull();
        expect(range!.toString()).toBe(expected);
        const back = rangeToSelection(root, range!, content);
        const trimmed = expected.trim();
        if (trimmed === "") {
          expect(back).toBeNull();
        } else {
          expect(back!.quote).toBe(trimmed);
          expect(cpSlice(content, back!.start, back!.end)).toBe(trimmed);
          if (trimmed === expected) expect(back).toEqual({ start: s, end: e, quote: expected });
        }
      }
    }
  });

  it("returns null for empty or out-of-range offsets", () => {
    const content = "abc";
    const root = renderMd(content);
    expect(offsetsToRange(root, content, 1, 1)).toBeNull();
    expect(offsetsToRange(root, content, 2, 1)).toBeNull();
    expect(offsetsToRange(root, content, 5, 9)).toBeNull();
    expect(offsetsToRange(root, "other", 0, 1)).toBeNull();
  });
});

describe("findAnchorRoot", () => {
  function setup() {
    const { container } = render(
      <div className="scope">
        <div className="user">a user message</div>
        <MessageContent content={"first **answer**\nline two"} messageId={10} selectable />
        <div className="chips">chip text</div>
        <MessageContent content={"second answer"} messageId={11} selectable />
        <MessageContent content={"branch answer"} messageId={12} />
      </div>,
    );
    const scope = container.querySelector<HTMLElement>(".scope")!;
    const roots = scope.querySelectorAll<HTMLElement>(".md");
    return { scope, a: roots[0], b: roots[1], plain: roots[2] };
  }

  it("accepts a range inside one selectable message", () => {
    const { scope, a } = setup();
    const found = findAnchorRoot(rangeBetween(a, "answer", "two"), scope)!;
    expect(found.root).toBe(a);
    expect(found.root.dataset.msgId).toBe("10");
  });

  it("rejects non-selectable messages and other elements", () => {
    const { scope, plain } = setup();
    const r = document.createRange();
    r.selectNodeContents(plain);
    expect(findAnchorRoot(r, scope)).toBeNull();
    r.selectNodeContents(scope.querySelector(".user")!);
    expect(findAnchorRoot(r, scope)).toBeNull();
  });

  it("rejects a range spanning two messages", () => {
    const { scope, a, b } = setup();
    const r = document.createRange();
    r.setStart(locate(a, "first")[0], 0);
    r.setEnd(locate(b, "second")[0], 3);
    expect(findAnchorRoot(r, scope)).toBeNull();
  });

  it("rejects a range that takes text from outside the message", () => {
    const { scope, a } = setup();
    const r = document.createRange();
    r.setStart(locate(a, "line two")[0], 0);
    r.setEnd(locate(scope.querySelector(".chips")!, "chip")[0], 4);
    expect(findAnchorRoot(r, scope)).toBeNull();
  });

  it("clips a range that ends just past the message without taking text", () => {
    const { scope, a } = setup();
    const content = "first **answer**\nline two";
    const r = document.createRange();
    r.setStart(locate(a, "line two")[0], 0);
    r.setEnd(scope.querySelector(".chips")!, 0);
    const found = findAnchorRoot(r, scope)!;
    expect(found.root).toBe(a);
    expect(rangeToSelection(found.root, found.range, content)!.quote).toBe("line two");
  });

  it("rejects collapsed ranges and roots outside the scope", () => {
    const { scope, a } = setup();
    const r = rangeBetween(a, "first", "first");
    const other = document.createElement("div");
    expect(findAnchorRoot(r, other)).toBeNull();
    r.collapse(true);
    expect(findAnchorRoot(r, scope)).toBeNull();
  });
});
