import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { DemoFrame } from "@/components/demo/DemoFrame";
import { SplitHeadline } from "@/components/ui/SplitHeadline";
import { Link, routing, type Locale } from "@/i18n/routing";
import { demoPath, hasDemo } from "@/lib/demos";
import { pageMetadata } from "@/lib/metadata";
import { getProject, getProjectSlugs } from "@/lib/projects";

type Props = { params: { locale: Locale; slug: string } };

export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = (await getProjectSlugs()).filter(hasDemo);
  return routing.locales.flatMap((locale) => slugs.map((slug) => ({ locale, slug })));
}

export async function generateMetadata({ params: { locale, slug } }: Props): Promise<Metadata> {
  const project = await getProject(slug, locale);
  if (!project) return {};
  const t = await getTranslations({ locale, namespace: "demo" });
  return pageMetadata({
    locale,
    path: demoPath(slug),
    title: `${t("label")} — ${project.title}`,
    description: project.summary,
    image: `/og/${locale}/projects/${slug}.png`,
  });
}

export default async function DemoPage({ params: { locale, slug } }: Props) {
  setRequestLocale(locale);
  const project = await getProject(slug, locale);
  if (!project || !hasDemo(slug)) notFound();
  const t = await getTranslations("demo");

  return (
    <article className="page-x pb-8 pt-10 md:pt-14">
      <div className="flex items-baseline justify-between border-b border-line pb-4">
        <Link href={`/projects/${slug}`} className="link-line font-mono text-label uppercase">
          ← {t("back")}
        </Link>
        <span className="font-mono text-label text-muted">{t("label")}</span>
      </div>
      <SplitHeadline
        text={project.title}
        className="mt-10 max-w-[12em] text-[clamp(2.25rem,5.5vw,4.5rem)] font-semibold leading-[0.98] tracking-[-0.045em] md:mt-14"
      />
      <p className="mt-5 max-w-2xl text-[1.0625rem] leading-relaxed text-muted">{t("lead")}</p>
      <div className="mt-8 border-t border-strong">
        <DemoFrame src={`/demos/${slug}/index.html?lang=${locale}`} title={t("frameTitle", { title: project.title })} />
      </div>
    </article>
  );
}
