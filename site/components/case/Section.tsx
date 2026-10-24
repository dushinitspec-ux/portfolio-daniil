import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

export const sectionIds = [
  "problem",
  "solution",
  "demo",
  "screenshots",
  "stack",
  "code",
  "bug",
  "result",
  "links",
] as const;
export type SectionId = (typeof sectionIds)[number];

/**
 * One section of a case study: a label in the left column, content on the right, separated
 * by a 1px rule. The label comes from messages/, so every case study uses the same wording.
 */
export async function Section({ id, children }: { id: SectionId; children: ReactNode }) {
  if (!sectionIds.includes(id)) throw new Error(`Unknown case-study section "${id}"`);
  const t = await getTranslations("case.sections");
  const number = String(sectionIds.indexOf(id) + 1).padStart(2, "0");
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid-12 gap-y-6 border-t border-line py-12 md:py-16">
      <h2 id={`${id}-title`} className="col-span-4 md:col-span-3">
        <span aria-hidden="true" className="block font-mono text-label text-muted">
          {number}
        </span>
        <span className="mt-2 block text-lg font-semibold tracking-tight">{t(id)}</span>
      </h2>
      <div data-reveal className="prose-case col-span-4 min-w-0 md:col-span-9 md:max-w-none">
        {children}
      </div>
    </section>
  );
}

/** A labelled part inside the bug section: what broke, root cause, the fix. */
export async function BugPart({
  id,
  children,
}: {
  id: "problem" | "cause" | "fix";
  children: ReactNode;
}) {
  const t = await getTranslations("case.bug");
  return (
    <div className="mt-8 grid gap-2 border-l-2 border-accent pl-5 md:grid-cols-[10rem_1fr] md:gap-6">
      <p className="font-mono text-label uppercase text-muted">{t(id)}</p>
      <div className="min-w-0 max-w-[37em]">{children}</div>
    </div>
  );
}
