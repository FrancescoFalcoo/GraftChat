import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MessageContent } from "../components/MessageContent";
import { linesText, parseMarkdown, splitLines } from "../markdown";

afterEach(cleanup);

function renderMd(content: string): HTMLElement {
  const { container } = render(<MessageContent content={content} messageId={1} selectable />);
  const el = container.querySelector<HTMLElement>(".md");
  if (!el) throw new Error("no .md element");
  return el;
}

const NASTY: [string, string][] = [
  ["empty string", ""],
  ["single newline", "\n"],
  ["only newlines", "\n\n\n"],
  ["no trailing newline", "hello"],
  ["trailing newline", "hello\n"],
  ["two trailing newlines", "hello\n\n"],
  ["leading newlines", "\n\nhello"],
  ["CRLF", "line one\r\nline two\r\n\r\nline four"],
  ["lone CR", "a\rb\r"],
  ["mixed EOL", "a\r\nb\nc\r"],
  ["whitespace only lines", "  \n\t\n "],
  ["bold", "some **bold** text"],
  ["italic star", "some *italic* text"],
  ["italic underscore", "some _italic_ text"],
  ["inline code", "call `foo()` now"],
  ["bold italic", "***both***"],
  ["nested", "**bold with *italic* and `code` inside**"],
  ["nested other way", "*it with **bold** inside*"],
  ["unclosed bold", "this **never closes"],
  ["unclosed italic", "this *never closes"],
  ["unclosed underscore", "this _never closes"],
  ["unclosed code", "this `never closes"],
  ["unbalanced runs", "**bold *it***"],
  ["stars with spaces", "2 * 3 * 4 and a * b"],
  ["star in words", "a*b*c and 2*3*4"],
  ["underscores in words", "snake_case_name and __init__ and a_b_c"],
  ["only markers", "** * _ ` *** **** ____ ``"],
  ["empty markers", "**** __ `` ``````"],
  ["markers in code", "`**not bold** _nor_ *this*`"],
  ["double backtick code", "``code with ` inside``"],
  ["escaped", "\\*not italic\\* and \\`not code\\` and \\\\"],
  ["trailing backslash", "ends with \\"],
  ["heading", "# Title\n## Sub **bold**\n###### Six\n####### Seven\n#NoSpace\n# "],
  ["heading with CRLF", "# Title\r\ntext"],
  ["lists", "- one\n* two\n+ three\n1. four\n2) five\n  - nested *it*\n- \n-not a list"],
  ["blockquote", "> quoted **text**\n>no space\n> \n>"],
  ["fenced code", "before\n```ts\nconst a = **b**;\n\n  indented `x`\n```\nafter"],
  ["fence never closed", "```\nline 1\nline 2 **x**\n"],
  ["fence never closed, no trailing newline", "```python\nprint('x')"],
  ["two fences back to back", "```\na\n```\n```\nb\n```"],
  ["only a fence", "```"],
  ["fence with backticks in info", "``` a`b\nnot code"],
  ["emoji", "hi \u{1F600} there \u{1F468}‍\u{1F469}‍\u{1F467} **bold \u{1F680}** done"],
  ["astral letters", "\u{1D573}\u{1D58A}\u{1D591}\u{1D591}\u{1D594} *\u{20000}* and _\u{1F600}_"],
  ["combining characters", "é café **ä** ñ ́leading"],
  ["lone surrogates", "bad \uD83D alone and \uDE00 too"],
  ["unicode line separators", "a b c\u0085d"],
  ["tabs and nbsp", "\ta b\t**c**\t"],
  ["html-like", "<b>not html</b> &amp; <script>alert(1)</script>"],
  ["very long line", "word ".repeat(5000) + "**end**"],
  ["many unmatched stars", "*a ".repeat(3000)],
  ["many unmatched backticks", "`a ".repeat(2999)],
  ["rtl and zero width", "שלום ​‏ *مرحبا* ﻿"],
  ["link syntax stays plain", "[text](http://example.com/a_b_c) ![img](x*y*z)"],
  ["table", "| a | b |\n|---|---|\n| *1* | `2` |"],
  ["horizontal rules", "---\n***\n___"],
];

describe("character-preserving renderer", () => {
  it.each(NASTY)("textContent === content: %s", (_name, content) => {
    expect(linesText(parseMarkdown(content))).toBe(content);
    const el = renderMd(content);
    expect(el.textContent).toBe(content);
    expect(el.querySelectorAll(".ln").length).toBe(splitLines(content).length);
  });

  it("holds for pseudo-random input", () => {
    const alphabet = [
      "a", "b", " ", " ", "\n", "\n", "\r\n", "*", "*", "**", "_", "`", "```", "#", "# ", "- ",
      "> ", "1. ", "\\", "\u{1F600}", "é", "\t", "~", "[", "]", "(", ")", "é", "\u{20000}",
    ];
    let seed = 42;
    const next = (): number => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 0x100000000;
    };
    for (let n = 0; n < 1500; n++) {
      const len = Math.floor(next() * 40);
      let s = "";
      for (let i = 0; i < len; i++) s += alphabet[Math.floor(next() * alphabet.length)];
      expect(linesText(parseMarkdown(s))).toBe(s);
      if (n % 25 === 0) {
        expect(renderMd(s).textContent).toBe(s);
        cleanup();
      }
    }
  });

  it("one .ln per source line, each ending with its own newline", () => {
    const el = renderMd("a\n\nb\r\nc");
    const texts = Array.from(el.querySelectorAll(".ln")).map((l) => l.textContent);
    expect(texts).toEqual(["a\n", "\n", "b\r\n", "c"]);
    expect(el.querySelectorAll(".ln")[1].className).toContain("ln-blank");
  });

  it("renders nothing for the empty string", () => {
    expect(renderMd("").childNodes.length).toBe(0);
  });
});

describe("markup recognition", () => {
  it("styles bold, italic and code and keeps the markers in .mk", () => {
    const el = renderMd("a **bold** b *it* c _it2_ d `code` e");
    expect(el.querySelector("strong")?.textContent).toBe("**bold**");
    expect(Array.from(el.querySelectorAll("em")).map((e) => e.textContent)).toEqual([
      "*it*",
      "_it2_",
    ]);
    expect(el.querySelector("code")?.textContent).toBe("`code`");
    const marks = Array.from(el.querySelectorAll(".mk")).map((m) => m.textContent);
    expect(marks).toEqual(["**", "**", "*", "*", "_", "_", "`", "`"]);
  });

  it("nests italic and code inside bold", () => {
    const el = renderMd("**bold with *italic* and `code` inside**");
    const strong = el.querySelector("strong");
    expect(strong?.querySelector("em")?.textContent).toBe("*italic*");
    expect(strong?.querySelector("code")?.textContent).toBe("`code`");
  });

  it("handles ***bold italic***", () => {
    const el = renderMd("***both***");
    expect(el.querySelector("strong > em")?.textContent).toBe("both");
  });

  it.each([
    ["unclosed bold", "this **never closes"],
    ["unclosed italic", "this *never closes"],
    ["unclosed code", "this `never closes"],
    ["spaced stars", "2 * 3 * 4"],
    ["star before space", "a * b* c"],
    ["intra-word stars", "2*3*4"],
    ["intra-word underscores", "snake_case_name"],
    ["dunder", "__init__"],
    ["closing underscore inside a word", "_a_b"],
    ["escaped stars", "\\*not italic\\*"],
    ["empty bold", "****"],
    ["unbalanced runs", "**bold *it***"],
  ])("leaves %s as plain text", (_name, content) => {
    const el = renderMd(content);
    expect(el.querySelector("strong, em, code, .mk")).toBeNull();
    expect(el.textContent).toBe(content);
  });

  it("does not parse markers inside inline code", () => {
    const el = renderMd("`**x** _y_`");
    expect(el.querySelector("strong, em")).toBeNull();
    expect(el.querySelector("code")?.textContent).toBe("`**x** _y_`");
  });

  it("does not let emphasis close inside a code span", () => {
    const el = renderMd("*a `b*` c");
    expect(el.querySelector("em")).toBeNull();
    expect(el.querySelector("code")?.textContent).toBe("`b*`");
  });

  it("recognises headings and hides the hashes", () => {
    const el = renderMd("## Title **x**\n#nope\n####### seven");
    const lines = el.querySelectorAll(".ln");
    expect(lines[0].className).toContain("ln-h2");
    expect(lines[0].querySelector(".mk")?.textContent).toBe("## ");
    expect(lines[0].querySelector("strong")).not.toBeNull();
    expect(lines[1].className).toContain("ln-p");
    expect(lines[2].className).toContain("ln-p");
  });

  it("recognises lists and blockquotes with visible markers", () => {
    const el = renderMd("- one\n  * two\n12. three\n> quote\n-nope");
    const lines = el.querySelectorAll(".ln");
    expect(lines[0].className).toContain("ln-li");
    expect(lines[0].querySelector(".lm")?.textContent).toBe("- ");
    expect(lines[1].querySelector(".lm")?.textContent).toBe("* ");
    expect(lines[2].querySelector(".lm")?.textContent).toBe("12. ");
    expect(lines[3].className).toContain("ln-bq");
    expect(lines[3].querySelector(".lm")?.textContent).toBe("> ");
    expect(lines[4].className).toContain("ln-p");
    expect(el.querySelector(".mk")).toBeNull();
  });

  it("treats everything inside a fence as code, closed or not", () => {
    const el = renderMd("x\n```js\n**a**\n# b\n```\n**y**");
    const kinds = Array.from(el.querySelectorAll(".ln")).map((l) => l.className);
    expect(kinds[0]).toContain("ln-p");
    expect(kinds[1]).toContain("ln-fence cb cb-first");
    expect(kinds[2]).toContain("ln-code");
    expect(kinds[3]).toContain("ln-code");
    expect(kinds[4]).toContain("ln-fence cb cb-last");
    expect(kinds[5]).toContain("ln-p");
    expect(el.querySelectorAll("strong").length).toBe(1);

    const open = renderMd("```\n**a**\nb");
    expect(open.querySelector("strong")).toBeNull();
    const openLines = open.querySelectorAll(".ln");
    expect(openLines[2].className).toContain("ln-code cb cb-last");
  });

  it("does not interpret HTML", () => {
    const el = renderMd("<b>x</b> <img src=x onerror=alert(1)>");
    expect(el.querySelector("b, img")).toBeNull();
  });
});
