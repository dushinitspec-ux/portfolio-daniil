import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ProjectCover } from "@/components/projects/ProjectCover";
import { SplitHeadline } from "@/components/ui/SplitHeadline";
import { Link, routing, type Locale } from "@/i18n/routing";
import { CaseStudyBody } from "@/lib/mdx";
import { pageMetadata } from "@/lib/metadata";
import { getProject, getProjects, getProjectSlugs } from "@/lib/projects";

type Props = { params: { locale: Locale; slug: string } };

export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = await getProjectSlugs();
  return routing.locales.flatMap((locale) => slugs.map((slug) => ({ locale, slug })));
}

export async function generateMetadata({ params: { locale, slug } }: Props): Promise<Metadata> {
  const project = await getProject(slug, locale);
  if (!project) return {};
  return pageMetadata({
    locale,
    path: `/projects/${slug}`,
    title: project.title,
    description: project.summary,
    image: `/og/${locale}/projects/${slug}.png`,
  });
}

export default async function CaseStudyPage({ params: { locale, slug } }: Props) {
  setRequestLocale(locale);
  const project = await getProject(slug, locale);
  if (!project) notFound();

  const t = await getTranslations("case");
  const tp = await getTranslations("projects");
  const all = await getProjects(locale);
  const index = all.findIndex((p) => p.slug === slug);
  const next = all[(index + 1) % all.length];

  const meta = [
    { label: t("role"), value: project.role },
    { label: t("year"), value: String(project.year) },
    { label: t("category"), value: project.categories.map((c) => tp(`categories.${c}`)).join(" · ") },
    { label: t("stack"), value: project.stack.slice(0, 4).join(", ") },
  ];

  return (
    <article>
      <header className="page-x pb-12 pt-10 md:pt-14">
        <div className="flex items-baseline justify-between border-b border-line pb-4">
          <Link href="/projects" className="link-line font-mono text-label uppercase">
            ← {t("back")}
          </Link>
          <span className="font-mono text-label text-muted">
            {String(project.order).padStart(2, "0")} / {String(all.length).padStart(2, "0")}
          </span>
        </div>
        <SplitHeadline
          text={project.title}
          className="mt-12 max-w-[9em] text-[clamp(2.75rem,7.5vw,7rem)] font-semibold leading-[0.96] tracking-[-0.05em] md:mt-16"
        />
        <p className="mt-8 max-w-2xl text-lg leading-relaxed text-muted md:text-xl">
          {project.summary}
        </p>
        <dl className="mt-12 grid grid-cols-2 border-l border-t border-line md:grid-cols-4">
          {meta.map((item) => (
            <div key={item.label} className="border-b border-r border-line p-4 md:p-5">
              <dt className="label">{item.label}</dt>
              <dd className="mt-2 text-[0.95rem]">{item.value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <div className="page-x">
        <ProjectCover image={project.cover} sizes="(min-width: 1440px) 1360px, 100vw" priority />
      </div>

      <div className="page-x mt-16">
        <CaseStudyBody project={project} />
      </div>

      {next && next.slug !== slug && (
        <nav aria-label={t("next")} className="page-x mt-16">
          <Link
            href={`/projects/${next.slug}`}
            className="group grid-12 border-t border-strong pt-8"
          >
            <span className="label col-span-4 md:col-span-3">{t("next")}</span>
            <span className="col-span-4 flex items-baseline justify-between gap-6 md:col-span-9">
              <span className="text-[clamp(2rem,5vw,4rem)] font-semibold leading-none tracking-[-0.04em]">
                <span className="link-line">{next.title}</span>
              </span>
              <span
                aria-hidden="true"
                className="text-3xl text-accent transition-transform duration-300 ease-out group-hover:translate-x-2"
              >
                →
              </span>
            </span>
          </Link>
        </nav>
      )}
    </article>
  );
}
