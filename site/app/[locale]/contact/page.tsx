import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ExternalLink } from "@/components/ui/ExternalLink";
import { PageHeader } from "@/components/ui/PageHeader";
import type { Locale } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { isPlaceholder, site } from "@/lib/site";

type Props = { params: { locale: Locale } };

export async function generateMetadata({ params: { locale } }: Props): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "meta" });
  return pageMetadata({
    locale,
    path: "/contact",
    title: t("contact"),
    description: t("contactDescription"),
  });
}

/** "https://t.me/name" -> "t.me/name": shorter to read, same link. */
function display(url: string): string {
  return isPlaceholder(url) ? url : url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}

export default async function ContactPage({ params: { locale } }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("contact");
  const channels = [
    { label: t("telegram"), href: site.telegram },
    { label: t("linkedin"), href: site.linkedin },
    { label: t("github"), href: site.github },
  ];

  return (
    <>
      <PageHeader index="/ 04" title={t("title")} lead={t("lead")} />
      <section className="page-x">
        <ul className="border-t border-line">
          <li className="grid-12 items-baseline gap-y-2 border-b border-line py-8">
            <span className="label col-span-4 md:col-span-3">{t("email")}</span>
            <a
              href={`mailto:${site.email}`}
              className="link-line col-span-4 justify-self-start break-all text-[clamp(1.5rem,4vw,3.25rem)] font-semibold tracking-[-0.03em] md:col-span-9"
            >
              {site.email}
            </a>
          </li>
          {channels.map((channel) => (
            <li
              key={channel.label}
              data-reveal
              className="grid-12 items-baseline gap-y-2 border-b border-line py-8"
            >
              <span className="label col-span-4 md:col-span-3">{channel.label}</span>
              <span className="col-span-4 text-[clamp(1.25rem,2.6vw,2rem)] font-semibold tracking-[-0.02em] md:col-span-9">
                <ExternalLink href={channel.href}>{display(channel.href)}</ExternalLink>
              </span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
