import type { ReactNode } from "react";

import { highlight } from "@/lib/highlight";

import { readCode } from "./code";
import { CopyButton } from "./CopyButton";

/** A fenced code block from MDX, highlighted with Shiki at build time, with a copy button. */
export async function CodeBlock(props: { children?: ReactNode }) {
  const raw = readCode(<pre {...props} />);
  if (!raw) return <pre>{props.children}</pre>;
  const html = await highlight(raw.code, raw.lang);

  return (
    <figure className="my-6 border border-line bg-surface">
      <figcaption className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <span className="font-mono text-label uppercase text-muted">{raw.lang}</span>
        <CopyButton code={raw.code} />
      </figcaption>
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </figure>
  );
}
