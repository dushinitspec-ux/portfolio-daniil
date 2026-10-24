import "server-only";

import fs from "node:fs/promises";
import path from "node:path";
import { cache } from "react";

import matter from "gray-matter";
import { z } from "zod";

import { routing, type Locale } from "@/i18n/routing";
import { categories } from "@/lib/site";

// Case studies live in content/projects/<slug>.<locale>.mdx. Adding a project means adding
// these files; no code changes. The frontmatter is validated here, so a typo fails the build
// with a clear message instead of rendering a broken page.
const CONTENT_DIR = path.join(process.cwd(), "content", "projects");

const imageSchema = z.object({
  src: z.string().startsWith("/"),
  alt: z.string().min(1),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  caption: z.string().optional(),
});

const frontmatterSchema = z.object({
  title: z.string().min(1),
  summary: z.string().min(1),
  categories: z.array(z.enum(categories)).min(1),
  order: z.number().int(),
  featured: z.boolean().default(false),
  year: z.number().int(),
  role: z.string().min(1),
  stack: z.array(z.string()).min(1),
  github: z.string().min(1),
  demo: z.string().min(1),
  video: z.string().startsWith("/").optional(),
  cover: imageSchema,
  screenshots: z.array(imageSchema).default([]),
});

export type ProjectImage = z.infer<typeof imageSchema>;
export type ProjectMeta = z.infer<typeof frontmatterSchema> & { slug: string; locale: Locale };
export type Project = ProjectMeta & { body: string };

async function readProject(slug: string, locale: Locale): Promise<Project> {
  const file = path.join(CONTENT_DIR, `${slug}.${locale}.mdx`);
  const raw = await fs.readFile(file, "utf8");
  const { data, content } = matter(raw);
  const parsed = frontmatterSchema.safeParse(data);
  if (!parsed.success) {
    throw new Error(`Invalid frontmatter in ${file}:\n${z.prettifyError(parsed.error)}`);
  }
  return { ...parsed.data, slug, locale, body: content };
}

export const getProjectSlugs = cache(async (): Promise<string[]> => {
  const files = await fs.readdir(CONTENT_DIR);
  const slugs = new Set(
    files
      .filter((f) => f.endsWith(`.${routing.defaultLocale}.mdx`))
      .map((f) => f.slice(0, -`.${routing.defaultLocale}.mdx`.length)),
  );
  // Every project must exist in every language, otherwise a page would 404 in one locale.
  for (const slug of slugs) {
    for (const locale of routing.locales) {
      if (!files.includes(`${slug}.${locale}.mdx`)) {
        throw new Error(`Missing translation: content/projects/${slug}.${locale}.mdx`);
      }
    }
  }
  return [...slugs];
});

export const getProject = cache(async (slug: string, locale: Locale): Promise<Project | null> => {
  const slugs = await getProjectSlugs();
  if (!slugs.includes(slug)) return null;
  return readProject(slug, locale);
});

export const getProjects = cache(async (locale: Locale): Promise<ProjectMeta[]> => {
  const slugs = await getProjectSlugs();
  const projects = await Promise.all(slugs.map((slug) => readProject(slug, locale)));
  return projects
    .map(({ body: _body, ...meta }) => meta)
    .sort((a, b) => a.order - b.order);
});
