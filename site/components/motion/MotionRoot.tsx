"use client";

import { useEffect } from "react";

import { usePathname } from "@/i18n/routing";

type Engine = {
  gsap: typeof import("gsap").gsap;
  ScrollTrigger: typeof import("gsap/ScrollTrigger").ScrollTrigger;
  lenis: import("lenis").default;
};

let engine: Promise<Engine> | null = null;
let lastPathname: string | null = null;

/**
 * GSAP, ScrollTrigger and Lenis are loaded only after the page has finished loading, so they
 * never compete with the first paint. Lenis gives smooth wheel scrolling; ScrollTrigger reads
 * Lenis' position so scroll-driven animations stay in sync.
 */
function loadEngine(): Promise<Engine> {
  engine ??= (async () => {
    const [{ gsap }, { ScrollTrigger }, { default: Lenis }] = await Promise.all([
      import("gsap"),
      import("gsap/ScrollTrigger"),
      import("lenis"),
    ]);
    gsap.registerPlugin(ScrollTrigger);
    const lenis = new Lenis({ duration: 1.05, anchors: true });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((time) => lenis.raf(time * 1000));
    gsap.ticker.lagSmoothing(0);
    return { gsap, ScrollTrigger, lenis };
  })();
  return engine;
}

function afterLoad(callback: () => void): () => void {
  if (document.readyState === "complete") {
    const id = window.setTimeout(callback, 0);
    return () => window.clearTimeout(id);
  }
  window.addEventListener("load", callback, { once: true });
  return () => window.removeEventListener("load", callback);
}

function inViewport(el: Element): boolean {
  const rect = el.getBoundingClientRect();
  return rect.top < window.innerHeight && rect.bottom > 0;
}

function animatePage({ gsap, ScrollTrigger }: Engine): () => void {
  // Reveals are started by an IntersectionObserver, not by ScrollTrigger: the observer fires
  // for every kind of scrolling (wheel, keyboard, anchor links, the browser's find-in-page),
  // so hidden content can never stay hidden.
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        const el = entry.target as HTMLElement;
        if ("mask" in el.dataset) {
          gsap.to(el.querySelector("[data-mask-inner]"), {
            yPercent: 0,
            scale: 1,
            duration: 1.2,
            ease: "expo.out",
          });
        } else {
          gsap.to(el, { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" });
        }
      }
    },
    { rootMargin: "0px 0px -8% 0px" },
  );

  const ctx = gsap.context(() => {
    // 1. Fade-and-rise reveals. Only elements below the fold are hidden, and only now that the
    //    script runs, so nothing on screen ever disappears and the page works without JS.
    for (const el of gsap.utils.toArray<HTMLElement>("[data-reveal]")) {
      if (inViewport(el)) continue;
      gsap.set(el, { opacity: 0, y: 24 });
      observer.observe(el);
    }

    // 2. Image / video reveal masks on project covers: the picture slides up inside its frame.
    for (const mask of gsap.utils.toArray<HTMLElement>("[data-mask]")) {
      const inner = mask.querySelector("[data-mask-inner]");
      if (!inner || inViewport(mask)) continue;
      gsap.set(inner, { yPercent: 18, scale: 1.12 });
      observer.observe(mask);
    }

    // 3. Pinned stack of featured projects (desktop): each card is sticky, and the card
    //    underneath shrinks and dims as the next one slides over it.
    const mm = gsap.matchMedia();
    mm.add("(min-width: 1024px)", () => {
      const cards = gsap.utils.toArray<HTMLElement>("[data-stack-card]");
      cards.forEach((card, i) => {
        const next = cards[i + 1];
        if (!next) return;
        gsap.to(card, {
          scale: 0.94,
          opacity: 0.45,
          transformOrigin: "50% 0%",
          ease: "none",
          scrollTrigger: { trigger: next, start: "top bottom", end: "top 30%", scrub: true },
        });
      });
    });
  });
  // Images and fonts change the page height; recalculate trigger positions once they settle.
  const refresh = window.setTimeout(() => ScrollTrigger.refresh(), 400);
  return () => {
    window.clearTimeout(refresh);
    observer.disconnect();
    ctx.revert();
  };
}

export function MotionRoot() {
  const pathname = usePathname();

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    const cancelWait = afterLoad(() => {
      loadEngine()
        .then((e) => {
          if (cancelled) return;
          // After client-side navigation start at the top; on first load keep the browser position.
          if (lastPathname !== null && lastPathname !== pathname) {
            e.lenis.scrollTo(0, { immediate: true });
          }
          lastPathname = pathname;
          cleanup = animatePage(e);
        })
        .catch(() => {
          // If a script fails to load, the page simply stays static and fully visible.
        });
    });
    return () => {
      cancelled = true;
      cancelWait();
      cleanup?.();
    };
  }, [pathname]);

  return null;
}
