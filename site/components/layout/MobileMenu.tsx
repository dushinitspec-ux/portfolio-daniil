"use client";

import { useEffect, useRef, useState } from "react";

import { Link, usePathname } from "@/i18n/routing";

import { isActive, type NavItem } from "./NavLinks";

export function MobileMenu({
  items,
  openLabel,
  closeLabel,
}: {
  items: NavItem[];
  openLabel: string;
  closeLabel: string;
}) {
  const [open, setOpen] = useState(false);
  // The overlay starts right under the header, wherever the header is on screen.
  const [top, setTop] = useState(0);
  const pathname = usePathname();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const firstLinkRef = useRef<HTMLAnchorElement>(null);

  // Close after navigating.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    firstLinkRef.current?.focus();
    document.documentElement.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.documentElement.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls="mobile-menu"
        onClick={() => {
          setTop(buttonRef.current?.closest("header")?.getBoundingClientRect().bottom ?? 0);
          setOpen((v) => !v);
        }}
        className="relative z-[60] font-mono text-label uppercase"
      >
        {open ? closeLabel : openLabel}
      </button>
      <div
        id="mobile-menu"
        hidden={!open}
        style={{ top }}
        className="fixed inset-x-0 bottom-0 z-50 bg-bg"
      >
        <nav className="page-x pt-10">
          <ul className="border-t border-line">
            {items.map((item, i) => (
              <li key={item.href} className="border-b border-line">
                <Link
                  ref={i === 0 ? firstLinkRef : undefined}
                  href={item.href}
                  aria-current={isActive(pathname, item.href) ? "page" : undefined}
                  className="flex items-baseline justify-between py-5 text-4xl font-semibold tracking-tight aria-[current=page]:text-accent-text"
                >
                  {item.label}
                  <span className="label">0{i + 1}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  );
}
