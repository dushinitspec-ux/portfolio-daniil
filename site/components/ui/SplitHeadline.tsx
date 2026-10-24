import { Fragment, type CSSProperties, type ElementType } from "react";

/**
 * A headline whose words rise one after another from behind a mask.
 *
 * - reveal="load": the words are split on the server and animated with CSS, so the effect
 *   starts on first paint with no JavaScript.
 * - reveal="scroll": the words start in place; MotionRoot hides them only if the headline is
 *   below the fold and raises them when it scrolls into view, so it never stays hidden.
 */
export function SplitHeadline({
  text,
  as: Tag = "h1",
  reveal = "load",
  className = "",
}: {
  text: string;
  as?: ElementType;
  reveal?: "load" | "scroll";
  className?: string;
}) {
  const words = text.split(" ");
  const wordClass = reveal === "load" ? "split-word" : "split-word-scroll inline-block";
  return (
    <Tag className={className} data-split={reveal === "scroll" ? "" : undefined}>
      {words.map((word, i) => (
        <Fragment key={i}>
          <span className="split-mask">
            <span
              className={`${wordClass} ${word === "—" ? "text-accent-text" : ""}`}
              style={reveal === "load" ? ({ "--i": i } as CSSProperties) : undefined}
            >
              {word}
            </span>
          </span>
          {i < words.length - 1 ? " " : null}
        </Fragment>
      ))}
    </Tag>
  );
}
