import type { ReactNode } from "react";

import { isPlaceholder } from "@/lib/site";

/**
 * A link to another site. While the URL is still a [placeholder], it renders as plain text
 * with a title hint, so the published site never contains a broken link.
 */
export function ExternalLink({
  href,
  children,
  className = "",
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  if (isPlaceholder(href)) {
    return (
      <span className={`text-muted ${className}`} title={href}>
        {children}
      </span>
    );
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`link-line ${className}`}>
      {children}
    </a>
  );
}
