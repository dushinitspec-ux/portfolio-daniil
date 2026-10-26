import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { FeaturedProjects } from "@/components/projects/FeaturedProjects";
import { ButtonLink } from "@/components/ui/ButtonLink";
import { Portrait } from "@/components/ui/Portrait";
import { SplitHeadline } from "@/components/ui/SplitHeadline";
import { Link, type Locale } from "@/i18n/routing";
import { pageMetadata } from "@/lib/metadata";
import { getProjects } from "@/lib/projects";
import { site } from "@/lib/site";
import { skillGroups, type SkillGroup } from "@/lib/skills";

type Props = { params: { locale: Locale } };

export async function generateMetadata({ params: { locale } }: Props): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: "meta" });
  return pageMetadata({ locale, path: "", title: t("title"), description: t("description") });
}

export default async function HomePage({ params: { locale } }: Props) {
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const featured = (await getProjects(locale)).filter((p) => p.featured).slice(0, 3);

  return (
    <>
      {/* Hero. While scrolling away it sinks and dims (data-layer) and the next section, which is
          painted above it, slides over it. */}
      <section data-layer className="page-x pb-20 pt-10 md:pb-28 md:pt-14">
        <div className="grid-12 gap-y-2 border-b border-line pb-4 font-mono text-label uppercase text-muted">
          <p className="col-span-4 md:col-span-4">{site.name}</p>
          <p className="col-span-4 md:col-span-4">{t("role")}</p>
          <p className="col-span-4 md:col-span-4 md:text-right">
            {t("place")} · {t("available")}
          </p>
        </div>

        {/* Desktop: headline on the left, a fixed column on the right (portrait, intro, buttons).
            Nothing sits under the headline, so when the web font replaces the fallback font and
            the headline re-wraps, no other element moves (no layout shift).
            Phones: portrait, headline, intro, buttons. */}
        <div className="mt-10 md:mt-16 md:flex md:items-start md:justify-between md:gap-12">
          <div data-depth className="mb-8 md:hidden">
            <Portrait alt={t("portraitAlt")} />
          </div>
          <SplitHeadline
            text={t("headline")}
            className="max-w-[8.4em] text-[clamp(2.6rem,7.2vw,7.25rem)] font-semibold leading-[0.98] tracking-[-0.045em]"
          />
          <div className="mt-12 md:mt-2 md:w-[clamp(15rem,24vw,22rem)] md:shrink-0">
            <div data-depth className="hidden md:block">
              <Portrait alt={t("portraitAlt")} />
            </div>
            <div className="hero-rise">
              <p className="text-[1.0625rem] leading-relaxed text-muted md:mt-12">{t("intro")}</p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <ButtonLink href="/projects">{t("ctaProjects")}</ButtonLink>
                <ButtonLink href="/contact" variant="outline">
                  {t("ctaContact")}
                </ButtonLink>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Selected work */}
      <section aria-labelledby="selected-work" className="page-x relative z-[1] bg-bg">
        <div data-rule className="flex items-baseline justify-between border-t border-strong pb-6 pt-5">
          <h2 id="selected-work" className="label text-fg">
            {t("selectedWork")}
          </h2>
          <Link href="/projects" className="link-line font-mono text-label uppercase">
            {t("allProjects")} →
          </Link>
        </div>
        <FeaturedProjects projects={featured} />
      </section>

      {/* Skills strip */}
      <section aria-labelledby="skills" className="page-x mt-24 md:mt-32">
        <h2 id="skills" data-rule className="label border-t border-strong pt-5 text-fg">
          {t("skillsTitle")}
        </h2>
        <div data-assemble className="mt-8 grid border-l border-t border-line md:grid-cols-3">
          {(Object.keys(skillGroups) as SkillGroup[]).map((group) => (
            <div key={group} data-assemble-item className="border-b border-r border-line bg-bg p-6 md:p-8">
              <h3 className="text-lg font-semibold tracking-tight">{t(`skillGroups.${group}`)}</h3>
              <ul className="mt-5 flex flex-wrap gap-x-4 gap-y-2 font-mono text-[0.8125rem] text-muted">
                {skillGroups[group].map((skill) => (
                  <li key={skill}>{skill}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Remote work call to action */}
      <section className="page-x mt-24 md:mt-36">
        <div data-rule className="grid-12 gap-y-8 border-t border-strong pt-10">
          <SplitHeadline
            as="p"
            reveal="scroll"
            text={t("remote")}
            className="col-span-4 text-[clamp(2rem,5vw,4.5rem)] font-semibold leading-[1.02] tracking-[-0.04em] md:col-span-9"
          />
          <div data-reveal className="col-span-4 md:col-span-5 md:col-start-8">
            <p className="text-muted">{t("remoteText")}</p>
            <div className="mt-8">
              <ButtonLink href={`mailto:${site.email}`}>{t("ctaContact")}</ButtonLink>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
