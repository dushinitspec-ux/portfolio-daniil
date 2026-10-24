import { getTranslations } from "next-intl/server";

import { ExternalLink } from "@/components/ui/ExternalLink";
import { Link } from "@/i18n/routing";
import { site } from "@/lib/site";

export async function SiteFooter() {
  const t = await getTranslations("footer");
  const nav = await getTranslations("nav");
  const c = await getTranslations("contact");

  return (
    <footer className="mt-32 border-t border-line">
      <div className="page-x grid-12 gap-y-10 py-12">
        <div className="col-span-4 md:col-span-5">
          <a
            href={`mailto:${site.email}`}
            className="link-line text-[clamp(1.5rem,3vw,2.25rem)] font-semibold tracking-tight"
          >
            {site.email}
          </a>
        </div>
        <ul className="col-span-2 space-y-2 md:col-span-2 md:col-start-7">
          {(["projects", "about", "cv", "contact"] as const).map((key) => (
            <li key={key}>
              <Link href={`/${key}`} className="link-line">
                {nav(key)}
              </Link>
            </li>
          ))}
        </ul>
        <ul className="col-span-2 space-y-2 md:col-span-2">
          <li>
            <ExternalLink href={site.telegram}>{c("telegram")}</ExternalLink>
          </li>
          <li>
            <ExternalLink href={site.linkedin}>{c("linkedin")}</ExternalLink>
          </li>
          <li>
            <ExternalLink href={site.github}>{c("github")}</ExternalLink>
          </li>
        </ul>
        <div className="col-span-4 flex flex-col justify-between gap-2 font-mono text-label text-muted md:col-span-12 md:flex-row">
          <p>
            © {new Date().getFullYear()} {t("rights")}
          </p>
          <p>
            {t("built")}{" "}
            <ExternalLink href={site.sourceCode} className="text-fg">
              {t("source")}
            </ExternalLink>
          </p>
        </div>
      </div>
    </footer>
  );
}
