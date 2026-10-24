import { getTranslations } from "next-intl/server";
import type { CSSProperties } from "react";

import { Link } from "@/i18n/routing";
import type { ProjectMeta } from "@/lib/projects";

import { ProjectCover } from "./ProjectCover";

/**
 * Featured projects as a pinned stack on desktop: every card sticks under the header and the
 * next one slides over it (MotionRoot shrinks the card underneath). On small screens they are a
 * plain list.
 */
export async function FeaturedProjects({ projects }: { projects: ProjectMeta[] }) {
  const t = await getTranslations("projects");
  return (
    <ol>
      {projects.map((project, i) => (
        <li
          key={project.slug}
          data-stack-card
          style={{ "--stack": i } as CSSProperties}
          className="border-t border-line bg-bg py-10 lg:sticky lg:top-[calc(var(--header-h)+var(--stack)*1.25rem)] lg:min-h-[70vh] lg:py-14"
        >
          <Link href={`/projects/${project.slug}`} className="group grid-12 gap-y-8">
            <div className="col-span-4 flex flex-col md:col-span-5">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-label text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="label">
                  {project.categories.map((c) => t(`categories.${c}`)).join(" · ")}
                </span>
              </div>
              <h3 className="mt-6 text-[clamp(1.9rem,3.6vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.03em]">
                {project.title}
              </h3>
              <p className="mt-5 max-w-md text-muted">{project.summary}</p>
              <p className="mt-6 font-mono text-label text-muted">
                {project.stack.slice(0, 4).join(" / ")}
              </p>
              <span className="mt-auto inline-flex items-center gap-2 pt-8 font-mono text-[0.8125rem] uppercase tracking-wide">
                <span className="link-line">{t("readCase")}</span>
                <span
                  aria-hidden="true"
                  className="text-accent transition-transform duration-300 ease-out group-hover:translate-x-1"
                >
                  →
                </span>
              </span>
            </div>
            <div className="col-span-4 md:col-span-7">
              <ProjectCover image={project.cover} sizes="(min-width: 768px) 58vw, 100vw" />
            </div>
          </Link>
        </li>
      ))}
    </ol>
  );
}
