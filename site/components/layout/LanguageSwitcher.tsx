"use client";

import { useLocale } from "next-intl";

import { Link, routing, usePathname } from "@/i18n/routing";

// Each language named in itself ("DE — Deutsch"); the visible code stays part of the name,
// so voice-control users can still say "click DE".
const NATIVE_NAMES: Record<string, string> = {
  en: "English",
  ru: "Русский",
  tr: "Türkçe",
  de: "Deutsch",
};

export function LanguageSwitcher({ label }: { label: string }) {
  const locale = useLocale();
  // The current path without the locale, e.g. "/projects/uptime-monitor".
  const pathname = usePathname();

  return (
    <nav aria-label={label}>
      <ul className="flex items-center font-mono text-label uppercase">
        {routing.locales.map((l, i) => (
          <li key={l} className="flex items-center">
            {i > 0 && (
              <span aria-hidden="true" className="px-1.5 text-muted/50">
                /
              </span>
            )}
            <Link
              href={pathname}
              locale={l}
              hrefLang={l}
              lang={l}
              aria-label={`${l.toUpperCase()} — ${NATIVE_NAMES[l]}`}
              aria-current={l === locale ? "true" : undefined}
              className={
                l === locale
                  ? "text-fg underline decoration-accent decoration-2 underline-offset-4"
                  : "text-muted transition-colors hover:text-fg"
              }
            >
              {l}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
