import { Fragment, type CSSProperties, type ElementType } from "react";

/**
 * A headline whose words rise one after another from behind a mask. The words are split on
 * the server and animated with CSS, so the effect starts on first paint with no JavaScript.
 */
export function SplitHeadline({
  text,
  as: Tag = "h1",
  className = "",
}: {
  text: string;
  as?: ElementType;
  className?: string;
}) {
  const words = text.split(" ");
  return (
    <Tag className={className}>
      {words.map((word, i) => (
        <Fragment key={i}>
          <span className="split-mask">
            <span
              className={`split-word ${word === "—" ? "text-accent-text" : ""}`}
              style={{ "--i": i } as CSSProperties}
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
