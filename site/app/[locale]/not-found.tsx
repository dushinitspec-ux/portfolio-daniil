import { getTranslations } from "next-intl/server";

import { ButtonLink } from "@/components/ui/ButtonLink";

export default async function NotFound() {
  const t = await getTranslations("notFound");
  return (
    <section className="page-x flex min-h-[70vh] flex-col justify-center py-20">
      <p
        aria-hidden="true"
        className="select-none text-[clamp(7rem,28vw,22rem)] font-semibold leading-[0.8] tracking-[-0.07em] text-fg/10"
      >
        {t("code")}
      </p>
      <h1 className="mt-6 text-[clamp(2rem,5vw,4rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
        {t("title")}
      </h1>
      <p className="mt-4 max-w-md text-lg text-muted">{t("text")}</p>
      <div className="mt-10">
        <ButtonLink href="/">{t("home")}</ButtonLink>
      </div>
    </section>
  );
}
