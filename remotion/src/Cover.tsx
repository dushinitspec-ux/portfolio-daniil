import { AbsoluteFill } from "remotion";

import { Label } from "./components";
import { projects, type ProjectId } from "./projects";
import { colors, mono, sans } from "./theme";

// Cover images for the project cards (16:10). Each has a simple drawn motif; these are
// illustrations, the real screenshots are on the case-study pages. No title or summary here:
// the card shows them right under the image, and one cover serves all four languages.

function FridgeMotif() {
  // A temperature line that crosses the dashed 5 °C limit and comes back.
  const points = [
    [0, 330], [120, 320], [200, 300], [240, 250], [270, 318], [380, 325], [470, 300],
    [540, 210], [600, 130], [650, 90], [700, 120], [760, 260], [820, 318], [960, 322],
  ];
  const path = points.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  return (
    <svg viewBox="0 0 960 420" width={960} height={420}>
      <clipPath id="above">
        <rect x="0" y="0" width="960" height="200" />
      </clipPath>
      <path d={`${path} L960 420 L0 420 Z`} fill={colors.accent} opacity={0.18} clipPath="url(#above)" />
      <line x1="0" x2="960" y1="200" y2="200" stroke={colors.accent} strokeWidth="3" strokeDasharray="14 12" />
      <path d={path} fill="none" stroke={colors.fg} strokeWidth="5" strokeLinejoin="round" />
      <text x="960" y="186" textAnchor="end" fontFamily={mono} fontSize="26" fill={colors.muted}>
        LIMIT 5.0 °C
      </text>
    </svg>
  );
}

function ConciergeMotif() {
  const lines = [
    { lang: "EN", text: "What time is breakfast?" },
    { lang: "RU", text: "Какой пароль от вайфая?" },
    { lang: "TR", text: "Havuz saat kaçta açılıyor?" },
    { lang: "DE", text: "Wann gibt es Frühstück?" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, width: 900 }}>
      {lines.map((line, i) => (
        <div key={line.lang} style={{ display: "flex", justifyContent: i % 2 ? "flex-start" : "flex-end" }}>
          <div
            style={{
              display: "flex",
              gap: 22,
              alignItems: "baseline",
              background: i === 1 ? colors.fg : "#FFFFFF",
              color: i === 1 ? colors.bg : colors.fg,
              border: `1px solid ${colors.line}`,
              padding: "22px 30px",
              fontSize: 40,
              letterSpacing: "-0.02em",
            }}
          >
            <span style={{ fontFamily: mono, fontSize: 22, opacity: 0.6 }}>{line.lang}</span>
            {line.text}
          </div>
        </div>
      ))}
    </div>
  );
}

function UptimeMotif() {
  // 24 hourly bars; one hour with an outage.
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-end", height: 260 }}>
      {Array.from({ length: 24 }, (_, i) => (
        <div
          key={i}
          style={{
            width: 28,
            height: 260,
            background: i === 17 ? colors.accent : i === 9 ? "#E2A21B" : colors.green,
            opacity: i === 17 ? 1 : 0.85,
          }}
        />
      ))}
    </div>
  );
}

const motifs: Record<ProjectId, () => JSX.Element> = {
  "fridge-alert-bot": FridgeMotif,
  "hotel-ai-concierge": ConciergeMotif,
  "uptime-monitor": UptimeMotif,
};

export function Cover({ project }: { project: ProjectId }) {
  const p = projects[project];
  const Motif = motifs[project];
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.bg,
        color: colors.fg,
        fontFamily: sans,
        padding: "90px 110px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", borderBottom: `1px solid ${colors.line}`, paddingBottom: 22 }}>
        <Label>Project {p.index}</Label>
        <div style={{ width: 18, height: 18, background: colors.accent }} />
      </div>
      <div style={{ display: "flex", flex: 1, alignItems: "center", justifyContent: "center", transform: "scale(1.45)" }}>
        <Motif />
      </div>
    </AbsoluteFill>
  );
}
