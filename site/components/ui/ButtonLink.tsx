import type { ReactNode } from "react";

import { Magnetic } from "@/components/motion/Magnetic";
import { Link } from "@/i18n/routing";

const styles = {
  solid: "bg-fg text-bg hover:bg-accent hover:text-[#111]",
  outline: "border border-strong text-fg hover:bg-fg hover:text-bg",
};

function Arrow() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="14"
      height="14"
      aria-hidden="true"
      className="transition-transform duration-300 ease-out group-hover:translate-x-1"
    >
      <path d="M1 8h13M9 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/** A button-styled link with a magnetic hover. Internal paths go through the locale-aware Link. */
export function ButtonLink({
  href,
  children,
  variant = "solid",
  download = false,
}: {
  href: string;
  children: ReactNode;
  variant?: keyof typeof styles;
  download?: boolean;
}) {
  const className = `group inline-flex items-center gap-3 px-5 py-3.5 font-mono text-[0.8125rem] uppercase tracking-wide transition-colors duration-200 ${styles[variant]}`;
  const internal = href.startsWith("/") && !download && !/\.[a-z0-9]+$/i.test(href);
  return (
    <Magnetic>
      {internal ? (
        <Link href={href} className={className}>
          {children}
          <Arrow />
        </Link>
      ) : (
        <a href={href} className={className} download={download || undefined}>
          {children}
          <Arrow />
        </a>
      )}
    </Magnetic>
  );
}
