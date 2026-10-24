"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

export function CopyButton({ code }: { code: string }) {
  const t = useTranslations("case");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(id);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // Clipboard blocked (e.g. insecure context): nothing to do, the code is still selectable.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="font-mono text-label uppercase text-muted transition-colors hover:text-fg"
    >
      <span aria-live="polite">{copied ? t("copied") : t("copy")}</span>
    </button>
  );
}
