import Image, { getImageProps } from "next/image";
import { getTranslations } from "next-intl/server";

import { ExternalLink } from "@/components/ui/ExternalLink";
import { Link } from "@/i18n/routing";
import type { Project } from "@/lib/projects";
import { isPlaceholder } from "@/lib/site";

// Blocks whose content comes from the frontmatter, so the MDX body only says where they go.

export async function Demo({ project }: { project: Project }) {
  const t = await getTranslations("case");
  if (!project.video) return null;
  // The poster goes through the Next.js image optimiser too (WebP/AVIF, resized), instead of
  // shipping the full-size PNG cover.
  const poster = getImageProps({ src: project.cover.src, alt: "", width: 1280, height: 800 }).props
    .src;
  return (
    <figure>
      <video
        controls
        playsInline
        preload="none"
        poster={poster}
        className="aspect-video w-full border border-line bg-surface"
      >
        <source src={project.video} type="video/mp4" />
        {t("videoFallback")}
      </video>
      <figcaption className="mt-3 font-mono text-label text-muted">{t("videoCaption")}</figcaption>
    </figure>
  );
}

export function Screenshots({ project }: { project: Project }) {
  return (
    <div className="grid gap-6">
      {project.screenshots.map((shot) => (
        <figure key={shot.src}>
          <div className="overflow-hidden border border-line bg-surface">
            <Image
              src={shot.src}
              alt={shot.alt}
              width={shot.width}
              height={shot.height}
              sizes="(min-width: 768px) 70vw, 100vw"
              className="h-auto w-full"
            />
          </div>
          {shot.caption && (
            <figcaption className="mt-3 font-mono text-label text-muted">{shot.caption}</figcaption>
          )}
        </figure>
      ))}
    </div>
  );
}

export function Stack({ project }: { project: Project }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {project.stack.map((item) => (
        <li
          key={item}
          className="border border-line px-3 py-1.5 font-mono text-[0.8125rem]"
        >
          {item}
        </li>
      ))}
    </ul>
  );
}

export async function Links({ project, demoHref }: { project: Project; demoHref?: string }) {
  const t = await getTranslations("case");
  const links = [
    { label: t("github"), href: project.github },
    // A project with an in-browser demo links to its demo page instead of the frontmatter value.
    { label: t("liveDemo"), href: demoHref ?? project.demo },
  ];
  return (
    <ul className="border-t border-line">
      {links.map((link) => (
        <li key={link.label} className="border-b border-line">
          <div className="flex items-baseline justify-between gap-4 py-4 text-lg">
            {link.href.startsWith("/") ? (
              <Link href={link.href} className="link-line">
                {link.label}
              </Link>
            ) : (
              <ExternalLink href={link.href}>{link.label}</ExternalLink>
            )}
            <span className="font-mono text-label text-muted">
              {isPlaceholder(link.href) ? t("placeholderLink") : link.href.startsWith("/") ? "→" : "↗"}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
