import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import type { Locale } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";

type Props = { params: { locale: Locale } };

const jobs = ["steady", "freelance", "family"] as const;
const languages = ["ru", "en", "tr"] as const;

export async function generateMetadata({ params: { locale } }: Props): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "meta" });
  return pageMetadata({
    locale,
    path: "/about",
    title: t("about"),
    description: t("aboutDescription"),
  });
}

export default async function AboutPage({ params: { locale } }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("about");

  return (
    <>
      <PageHeader index="/ 02" title={t("title")} lead={t("lead")} />

      <section aria-labelledby="how" className="page-x">
        <div data-rule className="grid-12 gap-y-6 border-t border-line py-12 md:py-16">
          <h2 id="how" className="col-span-4 text-lg font-semibold tracking-tight md:col-span-3">
            {t("howTitle")}
          </h2>
          <p
            data-reveal
            className="col-span-4 max-w-[26em] text-[clamp(1.35rem,2.4vw,2rem)] font-medium leading-snug tracking-[-0.02em] md:col-span-9"
          >
            {t("how")}
          </p>
        </div>
      </section>

      <section aria-labelledby="experience" className="page-x">
        <div data-rule className="grid-12 gap-y-6 border-t border-line py-12 md:py-16">
          <h2
            id="experience"
            className="col-span-4 text-lg font-semibold tracking-tight md:col-span-3"
          >
            {t("experienceTitle")}
          </h2>
          <ol className="col-span-4 md:col-span-9">
            {jobs.map((job) => (
              <li
                key={job}
                data-reveal
                className="grid gap-x-6 gap-y-2 border-b border-line py-8 first:pt-0 md:grid-cols-[11rem_1fr]"
              >
                <p className="font-mono text-label uppercase text-muted">
                  {t(`jobs.${job}.period`)}
                </p>
                <div>
                  <h3 className="text-xl font-semibold tracking-tight">{t(`jobs.${job}.title`)}</h3>
                  <p className="mt-1 text-muted">{t(`jobs.${job}.org`)}</p>
                  <p className="mt-4 max-w-[34em] leading-relaxed">{t(`jobs.${job}.text`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section aria-labelledby="languages" className="page-x">
        <div data-rule className="grid-12 gap-y-6 border-t border-line py-12 md:py-16">
          <h2
            id="languages"
            className="col-span-4 text-lg font-semibold tracking-tight md:col-span-3"
          >
            {t("languagesTitle")}
          </h2>
          <ul className="col-span-4 grid gap-px border border-line bg-[rgb(var(--fg)/0.14)] sm:grid-cols-3 md:col-span-9">
            {languages.map((lang) => (
              <li key={lang} data-reveal className="bg-bg p-6 text-lg">
                {t(`languages.${lang}`)}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="relocation" className="page-x">
        <div data-rule className="grid-12 gap-y-6 border-t border-strong py-12 md:py-16">
          <h2
            id="relocation"
            className="col-span-4 text-[clamp(2rem,5vw,4rem)] font-semibold leading-[1.02] tracking-[-0.04em] md:col-span-7"
          >
            {t("relocationTitle")}
            <span aria-hidden="true" className="text-accent-text">
              .
            </span>
          </h2>
          <p className="col-span-4 self-end text-lg text-muted md:col-span-5">
            {t("relocationText")}
          </p>
        </div>
      </section>
    </>
  );
}
