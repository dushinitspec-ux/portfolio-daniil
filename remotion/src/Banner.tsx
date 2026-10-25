import { AbsoluteFill } from "remotion";

import { colors, mono, sans } from "./theme";

// LinkedIn background image (1584×396). Dark version of the site's style. The text block starts
// at x≈440: on desktop LinkedIn the round profile photo covers the lower left of the banner.
const dark = { bg: "#111110", fg: "#EDEAE3", muted: "#A39E94" };

export function LinkedInBanner() {
  const label = { fontFamily: mono, fontSize: 19, letterSpacing: "0.06em", textTransform: "uppercase" as const, color: dark.muted };
  return (
    <AbsoluteFill style={{ backgroundColor: dark.bg, color: dark.fg, fontFamily: sans }}>
      <div
        style={{
          position: "absolute",
          left: 440,
          right: 80,
          top: 62,
          bottom: 56,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}
      >
        <div style={{ ...label, display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ width: 14, height: 14, background: colors.accent, display: "inline-block" }} />
          AI developer · IT &amp; networks · Antalya → EU
        </div>
        <div style={{ fontSize: 50, fontWeight: 600, lineHeight: 1.04, letterSpacing: "-0.035em" }}>
          I build AI tools that save businesses time <span style={{ color: colors.accent }}>—</span>
          <br />
          and I set up the hardware they run on.
        </div>
        <div style={{ ...label, display: "flex", justifyContent: "space-between", borderTop: `1px solid rgba(237,234,227,0.18)`, paddingTop: 16 }}>
          <span>10 projects · live demos in the browser</span>
          <span>Open to relocation &amp; remote</span>
        </div>
      </div>
    </AbsoluteFill>
  );
}
