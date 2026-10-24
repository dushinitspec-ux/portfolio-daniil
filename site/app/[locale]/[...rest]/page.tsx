import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { isLocale, routing } from "@/i18n/routing";

export async function generateMetadata({
  params: { locale },
}: {
  params: { locale: string };
}): Promise<Metadata> {
  const t = await getTranslations({
    locale: isLocale(locale) ? locale : routing.defaultLocale,
    namespace: "meta",
  });
  return { title: t("notFound"), robots: { index: false } };
}

// Any unknown path inside a locale (/en/whatever) renders the localised not-found page.
export default function CatchAll() {
  notFound();
}
