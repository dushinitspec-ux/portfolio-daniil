"use client";

import { LazyMotion, m, useReducedMotion } from "framer-motion";
import { useEffect, useState, type ReactNode } from "react";

// The first page load is never animated: content must be visible on first paint (and before
// any JavaScript runs). Only later client-side navigations fade in.
let isFirstLoad = true;

const loadFeatures = () => import("framer-motion").then((mod) => mod.domAnimation);

export function PageTransition({ children }: { children: ReactNode }) {
  const [animate] = useState(() => !isFirstLoad);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    isFirstLoad = false;
  }, []);

  if (!animate || reduceMotion) return <>{children}</>;

  return (
    <LazyMotion features={loadFeatures} strict>
      <m.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.26, ease: [0.2, 0.7, 0.1, 1] }}
      >
        {children}
      </m.div>
    </LazyMotion>
  );
}
