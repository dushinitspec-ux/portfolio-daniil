import Link from "next/link";

// Shown only for paths outside every locale (the middleware sends almost everything to /en,
// /ru, ...). Localised 404 pages live in app/[locale]/not-found.tsx.
export default function RootNotFound() {
  return (
    <html lang="en">
      <body className="flex min-h-screen items-center bg-bg px-4 font-sans text-fg">
        <main className="page-x">
          <p className="label">404</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight">This page does not exist.</h1>
          <Link className="link-line mt-8 inline-block" href="/en">
            Back to the home page
          </Link>
        </main>
      </body>
    </html>
  );
}
