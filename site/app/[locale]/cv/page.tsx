import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ButtonLink } from "@/components/ui/ButtonLink";
import { PageHeader } from "@/components/ui/PageHeader";
import type { Locale } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { cvFiles } from "@/lib/site";

type Props = { params: { locale: Locale } };

export async function generateMetadata({ params: { locale } }: Props): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "meta" });
  return pageMetadata({ locale, path: "/cv", title: t("cv"), description: t("cvDescription") });
}

export default async function CvPage({ params: { locale } }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("cv");

  return (
    <>
      <PageHeader index="/ 03" title={t("title")} lead={t("intro")} />
      <section className="page-x">
        <ol className="border-t border-line">
          {cvFiles.map((cv, i) => (
            <li key={cv.id} data-reveal className="grid-12 items-center gap-y-5 border-b border-line py-8 md:py-10">
              <span className="col-span-4 font-mono text-label text-muted md:col-span-1">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="col-span-4 md:col-span-7">
                <h2 className="text-[clamp(1.6rem,3vw,2.5rem)] font-semibold leading-tight tracking-[-0.03em]">
                  {t(`items.${cv.id}.title`)}
                </h2>
                <p className="mt-2 text-muted">{t(`items.${cv.id}.text`)}</p>
              </div>
              <div className="col-span-4 md:col-span-4 md:justify-self-end">
                <ButtonLink href={cv.file} variant="outline" download>
                  {t("download")}
                </ButtonLink>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
