import type { ReactNode } from "react";

import "./globals.css";

// The real root layout with <html> is app/[locale]/layout.tsx, because the language is part of
// the URL. This file only exists so that app/not-found.tsx can render for unknown paths.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
