"use client";

import { useEffect, useRef, useState } from "react";

const currentTheme = () => (document.documentElement.classList.contains("dark") ? "dark" : "light");

/**
 * The demo page in an iframe. The frame grows with its content (the demo reports its height),
 * so the site scrolls instead of the frame, and it follows the site's theme switch.
 * The src is set after mount, when the theme is known, so the demo starts with the right colours.
 */
export function DemoFrame({ src, title }: { src: string; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [url, setUrl] = useState<string>();
  const [height, setHeight] = useState(640);

  useEffect(() => {
    setUrl(`${src}${src.includes("?") ? "&" : "?"}theme=${currentTheme()}`);

    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.data?.type !== "demo:height") return;
      setHeight(Math.max(480, Math.ceil(Number(event.data.height) || 0)));
    };
    window.addEventListener("message", onMessage);

    const themeObserver = new MutationObserver(() => {
      frame.current?.contentWindow?.postMessage({ type: "theme", theme: currentTheme() }, window.location.origin);
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      window.removeEventListener("message", onMessage);
      themeObserver.disconnect();
    };
  }, [src]);

  return (
    <iframe
      ref={frame}
      src={url}
      title={title}
      style={{ height }}
      className="block w-full border-0 bg-bg"
      allow="clipboard-write"
    />
  );
}
