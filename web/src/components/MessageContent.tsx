import { Fragment, memo, useMemo, type ReactNode } from "react";
import { parseMarkdown, type Inline, type Line } from "../markdown";

interface Props {
  content: string;
  messageId: number;
  /** True only for assistant messages on main: marks the element as a branch anchor root. */
  selectable?: boolean;
}

function renderInline(parts: Inline[]): ReactNode[] {
  return parts.map((p, i) => {
    switch (p.t) {
      case "text":
        return <Fragment key={i}>{p.s}</Fragment>;
      case "mk":
        return (
          <span key={i} className="mk">
            {p.s}
          </span>
        );
      case "marker":
        return (
          <span key={i} className="lm">
            {p.s}
          </span>
        );
      case "strong":
        return <strong key={i}>{renderInline(p.c)}</strong>;
      case "em":
        return <em key={i}>{renderInline(p.c)}</em>;
      case "code":
        return <code key={i}>{renderInline(p.c)}</code>;
    }
  });
}

function lineClass(line: Line, isLast: boolean): string {
  const cls = ["ln", `ln-${line.kind}`];
  if (line.kind === "h") cls.push(`ln-h${line.level}`);
  if (line.kind === "fence" || line.kind === "code") {
    cls.push("cb");
    if (line.fence === "open") cls.push("cb-first");
    if (line.fence === "close" || isLast) cls.push("cb-last");
  }
  return cls.join(" ");
}

/**
 * Renders a message so that the element's textContent is exactly `content`
 * (one <div class="ln"> per source line, every source character in a text node).
 */
export const MessageContent = memo(function MessageContent({
  content,
  messageId,
  selectable = false,
}: Props) {
  const lines = useMemo(() => parseMarkdown(content), [content]);
  return (
    <div className="md" data-msg-id={messageId} data-anchor-root={selectable ? "" : undefined}>
      {lines.map((line, i) => (
        <div key={i} className={lineClass(line, i === lines.length - 1)}>
          {renderInline(line.parts)}
        </div>
      ))}
    </div>
  );
});
