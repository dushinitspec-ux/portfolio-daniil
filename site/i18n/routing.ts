import { createNavigation } from "next-intl/navigation";
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "ru", "tr", "de"],
  defaultLocale: "en",
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];

export function isLocale(value: string): value is Locale {
  return (routing.locales as readonly string[]).includes(value);
}

// Locale-aware versions of Next.js navigation helpers: <Link href="/about"> becomes /ru/about.
export const { Link, redirect, usePathname, useRouter, getPathname } = createNavigation(routing);
