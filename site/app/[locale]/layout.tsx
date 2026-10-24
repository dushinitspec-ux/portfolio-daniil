import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { notFound } from "next/navigation";
import { type AbstractIntlMessages, NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { Intro } from "@/components/motion/Intro";
import { MotionRoot } from "@/components/motion/MotionRoot";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { isLocale, routing } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { site } from "@/lib/site";

// display "swap": the brand font always appears, even when it arrives after the first paint.
// ("optional" kept the fallback font for the whole visit whenever the font was a few ms late.)
// The home hero is laid out so that the headline re-wrapping on swap moves nothing else.
const sans = Inter_Tight({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-sans",
  display: "swap",
});

// next/font would fall back to (adjusted) Arial even for a monospace font; keep labels
// monospaced while JetBrains Mono is not loaded yet.
const mono = JetBrains_Mono({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-mono",
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Consolas", "Menlo", "monospace"],
  adjustFontFallback: false,
});

// Runs before the page paints, so a dark-mode visitor never sees a white flash.
const themeScript = `(function(){try{var s=localStorage.getItem("theme");var d=s?s==="dark":matchMedia("(prefers-color-scheme: dark)").matches;if(d)document.documentElement.classList.add("dark")}catch(e){}})()`;

// Also before the first paint: the opening curtain plays on the first page of a browser session
// and never with reduced motion. The class is removed once the curtain and the hero entrance
// (which waits for it) are over, so a later re-render cannot replay it.
const introScript = `(function(){try{var r=document.documentElement;if(sessionStorage.getItem("intro")||matchMedia("(prefers-reduced-motion: reduce)").matches)return;sessionStorage.setItem("intro","1");r.classList.add("intro");var t;function done(){clearTimeout(t);removeEventListener("animationend",end);setTimeout(function(){r.classList.remove("intro")},1500)}function end(e){if(e.animationName==="intro-lift"&&e.target.classList.contains("intro-accent"))done()}addEventListener("animationend",end);t=setTimeout(done,8000)}catch(e){}})()`;

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
  const home = await getTranslations("home");

  return (
    <html lang={locale} className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        {/* First thing in <body>: sets the theme (and the intro) before anything is painted. */}
        <script dangerouslySetInnerHTML={{ __html: `${themeScript};${introScript}` }} />
        <Intro label={home("introLabel")} role={home("role")} place={home("place")} />
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
