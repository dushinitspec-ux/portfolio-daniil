"use client";

import { Link, usePathname } from "@/i18n/routing";

export type NavItem = { href: string; label: string };

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavLinks({ items, label }: { items: NavItem[]; label: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="hidden md:block">
      <ul className="flex items-center gap-8 text-[0.95rem]">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="link-line"
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
