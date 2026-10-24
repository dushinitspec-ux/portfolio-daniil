import createMiddleware from "next-intl/middleware";

import { routing } from "./i18n/routing";

// Redirects "/" to the visitor's language (from the browser) and keeps the locale in every URL.
export default createMiddleware(routing);

export const config = {
  // Skip Next.js internals and any path with a file extension (images, PDFs, videos).
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
