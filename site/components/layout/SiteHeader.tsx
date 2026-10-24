import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { MobileMenu } from "./MobileMenu";
import { NavLinks, type NavItem } from "./NavLinks";
import { StatusLine } from "./StatusLine";
import { ThemeToggle } from "./ThemeToggle";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  const items: NavItem[] = [
    { href: "/projects", label: t("projects") },
    { href: "/about", label: t("about") },
    { href: "/cv", label: t("cv") },
    { href: "/contact", label: t("contact") },
  ];

  return (
    <>
      <StatusLine />
      <header className="sticky top-0 z-50 border-b border-line bg-bg">
        <div className="page-x flex h-[var(--header-h)] items-center justify-between gap-6">
          <Link
            href="/"
            className="group flex items-baseline gap-2 text-[0.95rem] font-semibold tracking-tight"
          >
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 translate-y-[-0.1em] bg-accent transition-transform duration-300 ease-out group-hover:rotate-45"
            />
            Daniil Dushin
          </Link>
          <NavLinks items={items} label={t("primary")} />
          <div className="flex items-center gap-3 sm:gap-5">
            <LanguageSwitcher label={t("language")} />
            <ThemeToggle toDark={t("themeToDark")} toLight={t("themeToLight")} />
            <MobileMenu items={items} openLabel={t("menu")} closeLabel={t("close")} />
          </div>
        </div>
      </header>
    </>
  );
}
