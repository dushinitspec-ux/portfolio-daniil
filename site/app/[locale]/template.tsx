import type { ReactNode } from "react";

import { PageTransition } from "@/components/motion/PageTransition";

// A template (unlike a layout) mounts again on every navigation, which is what lets each new
// page play its entrance transition.
export default function Template({ children }: { children: ReactNode }) {
  return <PageTransition>{children}</PageTransition>;
}
