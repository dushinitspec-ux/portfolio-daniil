import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ProjectGrid } from "@/components/projects/ProjectGrid";
import { PageHeader } from "@/components/ui/PageHeader";
import type { Locale } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { getProjects } from "@/lib/projects";

type Props = { params: { locale: Locale } };

export async function generateMetadata({ params: { locale } }: Props): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "meta" });
  return pageMetadata({
    locale,
    path: "/projects",
    title: t("projects"),
    description: t("projectsDescription"),
  });
}

export default async function ProjectsPage({ params: { locale } }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("projects");
  const projects = await getProjects(locale);

  return (
    <>
      <PageHeader index="/ 01" title={t("title")} lead={t("intro")} />
      <section className="page-x">
        <ProjectGrid projects={projects} />
      </section>
    </>
  );
}
