import { SplitHeadline } from "./SplitHeadline";

/** Title block shared by the inner pages: a small index label, a split headline and a lead. */
export function PageHeader({ index, title, lead }: { index: string; title: string; lead?: string }) {
  return (
    <header className="page-x pb-14 pt-10 md:pb-20 md:pt-14">
      <div className="flex items-baseline justify-between border-b border-line pb-4">
        <span className="font-mono text-label text-muted">{index}</span>
      </div>
      <div className="grid-12 mt-12 gap-y-8 md:mt-16">
        <SplitHeadline
          text={title}
          className="col-span-4 text-[clamp(2.75rem,8vw,7.5rem)] font-semibold leading-[0.95] tracking-[-0.05em] md:col-span-7"
        />
        {lead && (
          <p className="col-span-4 self-end text-[1.0625rem] leading-relaxed text-muted md:col-span-5 md:text-lg">
            {lead}
          </p>
        )}
      </div>
    </header>
  );
}
