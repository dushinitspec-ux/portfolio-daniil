import { getTranslations } from "next-intl/server";

export async function StatusLine() {
  const t = await getTranslations("status");
  return (
    <div className="border-b border-line">
      <p className="page-x flex items-center gap-2.5 py-2 font-mono text-label text-muted">
        <span aria-hidden="true" className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
        </span>
        <span>
          <span className="text-fg">{t("label")}:</span> {t("text")}
        </span>
      </p>
    </div>
  );
}
