"use client";

import { AnimatePresence, LazyMotion, m } from "framer-motion";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Link } from "@/i18n/routing";
import type { ProjectMeta } from "@/lib/projects";
import { categories, type Category } from "@/lib/site";

type Filter = Category | "all";

// Layout animations need the larger "domMax" feature set; it loads after the page is ready.
const loadFeatures = () => import("framer-motion").then((mod) => mod.domMax);

function readFilter(): Filter {
  const value = new URLSearchParams(window.location.search).get("category");
  return categories.find((c) => c.toLowerCase() === value) ?? "all";
}

export function ProjectGrid({ projects }: { projects: ProjectMeta[] }) {
  const t = useTranslations("projects");
  const [filter, setFilter] = useState<Filter>("all");

  // The filter lives in the URL (?category=bots) so a filtered view can be shared.
  useEffect(() => setFilter(readFilter()), []);

  function choose(next: Filter) {
    setFilter(next);
    const url = new URL(window.location.href);
    if (next === "all") url.searchParams.delete("category");
    else url.searchParams.set("category", next.toLowerCase());
    window.history.replaceState(null, "", url);
  }

  const visible =
    filter === "all" ? projects : projects.filter((p) => p.categories.includes(filter));
  const options: Filter[] = ["all", ...categories];

  return (
    <LazyMotion features={loadFeatures} strict>
      <div role="group" aria-label={t("filterLabel")} className="flex flex-wrap gap-2">
        {options.map((option) => {
          const count =
            option === "all"
              ? projects.length
              : projects.filter((p) => p.categories.includes(option)).length;
          const active = filter === option;
          return (
            <button
              key={option}
              type="button"
              aria-pressed={active}
              onClick={() => choose(option)}
              className={`border px-4 py-2 font-mono text-label uppercase transition-colors duration-200 ${
                active
                  ? "border-fg bg-fg text-bg"
                  : "border-line text-fg hover:border-fg"
              }`}
            >
              {option === "all" ? t("all") : t(`categories.${option}`)}{" "}
              <span className={active ? "ml-2 text-bg/70" : "ml-2 text-muted"}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* Framer animates the list items (filtering); MotionRoot assembles the links inside them
          on scroll, so the two never animate the same element. */}
      <m.ul layout data-assemble className="mt-10 grid gap-x-6 gap-y-14 md:grid-cols-2">
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((project) => (
            <m.li
              key={project.slug}
              layout
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ duration: 0.3, ease: [0.2, 0.7, 0.1, 1] }}
            >
              <Link href={`/projects/${project.slug}`} data-assemble-item className="group block">
                <div className="relative aspect-[16/10] overflow-hidden border border-line bg-surface">
                  <Image
                    src={project.cover.src}
                    alt={project.cover.alt}
                    fill
                    sizes="(min-width: 768px) 45vw, 100vw"
                    className="object-cover transition-transform duration-700 ease-out group-hover:scale-[1.03]"
                  />
                </div>
                <div className="mt-5 flex items-baseline justify-between gap-4">
                  <span className="font-mono text-label text-muted">
                    {String(project.order).padStart(2, "0")}
                  </span>
                  <span className="label text-right">
                    {project.categories.map((c) => t(`categories.${c}`)).join(" · ")}
                  </span>
                </div>
                <h2 className="mt-3 text-[clamp(1.6rem,2.6vw,2.25rem)] font-semibold leading-tight tracking-[-0.025em]">
                  <span className="link-line">{project.title}</span>
                </h2>
                <p className="mt-3 max-w-xl text-muted">{project.summary}</p>
              </Link>
            </m.li>
          ))}
        </AnimatePresence>
      </m.ul>

      {visible.length === 0 && <p className="mt-10 text-muted">{t("empty")}</p>}
    </LazyMotion>
  );
}
