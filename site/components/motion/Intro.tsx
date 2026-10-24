import { site } from "@/lib/site";

/**
 * Opening curtain, shown once per browser session. The inline script at the top of <body>
 * decides and adds `intro` to <html> before the first paint; without that class the curtain
 * stays `hidden`. Everything runs on CSS (see app/globals.css), so it starts on the first
 * frame, never waits for JavaScript, and ends on its own.
 */
export function Intro({ label, role, place }: { label: string; role: string; place: string }) {
  const [first, ...rest] = site.name.split(" ");
  return (
    <div hidden aria-hidden="true" className="intro">
      <div className="intro-accent" />
      <div className="intro-panel">
        <div className="intro-content page-x">
          <div className="intro-meta flex items-baseline justify-between font-mono text-label uppercase">
            <span className="flex items-baseline gap-2">
              <span className="inline-block h-2 w-2 bg-accent" />
              {label}
            </span>
            <span>{new Date().getFullYear()}</span>
          </div>
          <p className="intro-name">
            <span className="intro-line">
              <span>{first}</span>
            </span>
            <span className="intro-line">
              <span>{rest.join(" ")}</span>
            </span>
          </p>
          <span className="intro-bar" />
          <div className="intro-meta mt-4 flex items-baseline justify-between gap-6 font-mono text-label uppercase">
            <span>{role}</span>
            <span className="text-right">{place}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
