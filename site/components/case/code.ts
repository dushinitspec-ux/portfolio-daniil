import { isValidElement, type ReactNode } from "react";

export type RawCode = { code: string; lang: string };

/**
 * MDX turns a fenced code block into <pre><code className="language-python">…</code></pre>.
 * Read the raw text and the language back out of that element tree.
 */
export function readCode(pre: ReactNode): RawCode | null {
  if (!isValidElement<{ children?: ReactNode }>(pre)) return null;
  const code = pre.props.children;
  if (!isValidElement<{ className?: string; children?: ReactNode }>(code)) return null;
  const text = code.props.children;
  if (typeof text !== "string") return null;
  const lang = code.props.className?.replace(/^language-/, "") ?? "text";
  return { code: text.replace(/\n$/, ""), lang };
}
