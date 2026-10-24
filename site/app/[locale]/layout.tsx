import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { notFound } from "next/navigation";
import { type AbstractIntlMessages, NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { MotionRoot } from "@/components/motion/MotionRoot";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { isLocale, routing } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { site } from "@/lib/site";

// display "optional": the preloaded web font is used when it arrives within ~100 ms (almost
// always), otherwise the page keeps the fallback font for that visit. "swap" re-wrapped the big
// headline when the font arrived, a layout shift Lighthouse measured at 0.17.
const sans = Inter_Tight({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-sans",
  display: "optional",
});

const mono = JetBrains_Mono({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-mono",
  display: "optional",
});

// Runs before the page paints, so a dark-mode visitor never sees a white flash.
const themeScript = `(function(){try{var s=localStorage.getItem("theme");var d=s?s==="dark":matchMedia("(prefers-color-scheme: dark)").matches;if(d)document.documentElement.classList.add("dark")}catch(e){}})()`;

export const dynamicParams = false;

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F5F3EE" },
    { media: "(prefers-color-scheme: dark)", color: "#111110" },
  ],
};

export async function generateMetadata({
  params: { locale },
}: {
  params: { locale: string };
}): Promise<Metadata> {
  if (!isLocale(locale)) return {};
  const t = await getTranslations({ locale, namespace: "meta" });
  return {
    metadataBase: new URL(site.url),
    ...pageMetadata({ locale, path: "", title: t("title"), description: t("description") }),
    title: { default: t("title"), template: `%s — ${site.name}` },
    authors: [{ name: site.name }],
  };
}

export default async function LocaleLayout({
  children,
  params: { locale },
}: {
  children: ReactNode;
  params: { locale: string };
}) {
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  // Client components only need these namespaces; the rest stays on the server.
  const { nav, projects, case: caseStudy } = (await getMessages()) as Record<
    string,
    AbstractIntlMessages
  >;
  const messages = { nav, projects, case: caseStudy };
  const t = await getTranslations("nav");

  return (
    <html lang={locale} className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <NextIntlClientProvider messages={messages}>
          <a
            href="#main"
            className="fixed left-4 top-2 z-[100] -translate-y-20 bg-fg px-4 py-2 font-mono text-sm text-bg transition-transform focus:translate-y-0"
          >
            {t("skip")}
          </a>
          <SiteHeader />
          <main id="main" tabIndex={-1} className="outline-none">
            {children}
          </main>
          <SiteFooter />
          <MotionRoot />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
