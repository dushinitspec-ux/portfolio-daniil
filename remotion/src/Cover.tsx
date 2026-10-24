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

function Chip({ children, accent = false }: { children: string; accent?: boolean }) {
  return (
    <span
      style={{
        fontFamily: mono,
        fontSize: 30,
        padding: "4px 12px",
        background: accent ? colors.accent : colors.fg,
        color: colors.bg,
      }}
    >
      {children}
    </span>
  );
}

function PiiMotif() {
  // The same message before and after masking.
  const row = { display: "flex", gap: 14, alignItems: "baseline", flexWrap: "wrap" } as const;
  const box = { border: `1px solid ${colors.line}`, background: "#FFFFFF", padding: "28px 34px" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, width: 900, fontSize: 36 }}>
      <div style={box}>
        <div style={row}>
          Refund to <u style={{ textDecorationColor: colors.accent }}>DE89 3704 0044 0532 0130 00</u>
        </div>
        <div style={{ ...row, marginTop: 10 }}>
          and reply to <u style={{ textDecorationColor: colors.accent }}>anna@example.com</u>
        </div>
      </div>
      <div style={box}>
        <div style={row}>
          Refund to <Chip>{"<IBAN_1>"}</Chip>
        </div>
        <div style={{ ...row, marginTop: 10 }}>
          and reply to <Chip accent>{"<EMAIL_1>"}</Chip>
        </div>
      </div>
    </div>
  );
}

function InvoiceMotif() {
  // Invoice totals on the left, the UBL elements they become on the right.
  const lines = [
    ["Net", "1,000.00"],
    ["VAT 19 %", "190.00"],
    ["Total", "1,190.00"],
  ];
  const xml = [
    "<cbc:TaxExclusiveAmount>",
    "  1000.00",
    "<cbc:TaxAmount>",
    "  190.00",
    "<cbc:PayableAmount>",
    "  1190.00",
  ];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 46 }}>
      <div style={{ width: 360, background: "#FFFFFF", border: `1px solid ${colors.line}`, padding: "30px 34px" }}>
        <Label>Invoice</Label>
        {lines.map(([label, value], i) => (
          <div
            key={label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: 20,
              paddingTop: i === 2 ? 18 : 0,
              borderTop: i === 2 ? `2px solid ${colors.fg}` : "none",
              fontSize: 32,
              fontWeight: i === 2 ? 600 : 400,
            }}
          >
            <span>{label}</span>
            <span>{value}</span>
          </div>
        ))}
      </div>
      <div style={{ fontFamily: mono, fontSize: 60, color: colors.accent }}>→</div>
      <div style={{ fontFamily: mono, fontSize: 26, lineHeight: 1.55, whiteSpace: "pre" }}>
        {xml.map((line) => (
          <div key={line} style={{ color: line.startsWith("<") ? colors.muted : colors.fg }}>
            {line}
          </div>
        ))}
      </div>
    </div>
  );
}

function HelpdeskMotif() {
  // A question and a grounded answer with numbered sources.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, width: 900 }}>
      <div style={{ alignSelf: "flex-end", background: colors.fg, color: colors.bg, padding: "22px 30px", fontSize: 38 }}>
        How do I connect to the VPN?
      </div>
      <div style={{ background: "#FFFFFF", border: `1px solid ${colors.line}`, padding: "26px 32px", fontSize: 34, lineHeight: 1.4 }}>
        Open the VPN app and sign in with your work account <b style={{ color: colors.accent }}>[1]</b>, then
        approve the MFA prompt on your phone <b style={{ color: colors.accent }}>[2]</b>.
        <div style={{ display: "flex", gap: 34, marginTop: 20, fontFamily: mono, fontSize: 22, color: colors.muted }}>
          <span>[1] VPN · CONNECT FROM HOME</span>
          <span>[2] MFA · SET UP THE APP</span>
        </div>
      </div>
    </div>
  );
}

function NetworkMotif() {
  // Devices on a subnet; one new device with Telnet (tcp/23) open, flagged in the accent.
  const hosts = [1, 2, 5, 10, 11, 12, 20, 21, 22, 23, 30, 31, 40, 41, 50, 64, 77, 101];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 130px)", gap: 16 }}>
      {hosts.map((h) => {
        const flagged = h === 77;
        return (
          <div
            key={h}
            style={{
              height: 86,
              border: `2px solid ${flagged ? colors.accent : colors.line}`,
              background: flagged ? colors.accent : "#FFFFFF",
              color: flagged ? colors.bg : colors.muted,
              fontFamily: mono,
              fontSize: 22,
              padding: "12px 14px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <span>.{h}</span>
            {flagged && <span>tcp/23</span>}
          </div>
        );
      })}
    </div>
  );
}

function AccessibilityMotif() {
  const checks: [string, string, boolean][] = [
    ["1.1.1", "Non-text content", false],
    ["2.4.2", "Page titled", true],
    ["3.1.1", "Language of page", true],
    ["1.4.3", "Contrast (minimum)", false],
    ["2.4.4", "Link purpose", true],
  ];
  return (
    <div style={{ width: 860, borderTop: `2px solid ${colors.fg}` }}>
      {checks.map(([id, name, ok]) => (
        <div
          key={id}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 30,
            padding: "18px 0",
            borderBottom: `1px solid ${colors.line}`,
            fontSize: 36,
          }}
        >
          <span style={{ fontFamily: mono, fontSize: 26, color: colors.muted, width: 110 }}>{id}</span>
          <span style={{ flex: 1 }}>{name}</span>
          <span style={{ fontFamily: mono, fontSize: 26, color: ok ? colors.green : colors.accent }}>
            {ok ? "PASS" : "FAIL"}
          </span>
        </div>
      ))}
    </div>
  );
}

function EnergyMotif() {
  // An illustrative day-ahead price curve: expensive mornings and evenings, a cheap solar
  // midday. The four cheapest hours in a row are the plan.
  const prices = [62, 58, 55, 54, 56, 64, 88, 112, 104, 80, 52, 34, 22, 18, 20, 30, 58, 96, 124, 118, 98, 84, 74, 66];
  const cheapest = new Set([11, 12, 13, 14]);
  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", height: 300 }}>
        {prices.map((p, i) => (
          <div
            key={i}
            style={{
              width: 28,
              height: p * 2.3,
              background: cheapest.has(i) ? colors.accent : colors.fg,
              opacity: cheapest.has(i) ? 1 : 0.22,
            }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
        <Label style={{ fontSize: 20 }}>00:00</Label>
        <Label style={{ fontSize: 20 }}>12:00</Label>
        <Label style={{ fontSize: 20 }}>23:00</Label>
      </div>
    </div>
  );
}

function AllergenMotif() {
  // The 14 allergens of Annex II to Regulation (EU) No 1169/2011, in its order.
  const allergens = [
    "Gluten", "Crustaceans", "Eggs", "Fish", "Peanuts", "Soy", "Milk",
    "Nuts", "Celery", "Mustard", "Sesame", "Sulphites", "Lupin", "Molluscs",
  ];
  const marked = new Set([0, 2, 6]);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 128px)", gap: 14 }}>
      {allergens.map((name, i) => (
        <div
          key={name}
          style={{
            height: 120,
            padding: "12px 14px",
            border: `2px solid ${marked.has(i) ? colors.accent : colors.line}`,
            background: marked.has(i) ? colors.accent : "#FFFFFF",
            color: marked.has(i) ? colors.bg : colors.fg,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <span style={{ fontFamily: mono, fontSize: 30 }}>{i + 1}</span>
          <span style={{ fontSize: 19 }}>{name}</span>
        </div>
      ))}
    </div>
  );
}

// Projects 01–03 also have promo videos (projects.ts); 04–10 have covers only.
export type CoverId =
  | ProjectId
  | "pii-guard"
  | "e-invoice"
  | "helpdesk-copilot"
  | "network-inventory"
  | "accessibility-check"
  | "energy-saver"
  | "allergen-labels";

const covers: Record<CoverId, { index: string; Motif: () => JSX.Element }> = {
  "fridge-alert-bot": { index: projects["fridge-alert-bot"].index, Motif: FridgeMotif },
  "hotel-ai-concierge": { index: projects["hotel-ai-concierge"].index, Motif: ConciergeMotif },
  "uptime-monitor": { index: projects["uptime-monitor"].index, Motif: UptimeMotif },
  "pii-guard": { index: "04", Motif: PiiMotif },
  "e-invoice": { index: "05", Motif: InvoiceMotif },
  "helpdesk-copilot": { index: "06", Motif: HelpdeskMotif },
  "network-inventory": { index: "07", Motif: NetworkMotif },
  "accessibility-check": { index: "08", Motif: AccessibilityMotif },
  "energy-saver": { index: "09", Motif: EnergyMotif },
  "allergen-labels": { index: "10", Motif: AllergenMotif },
};

export const coverIds = Object.keys(covers) as CoverId[];

export function Cover({ project }: { project: CoverId }) {
  const { index, Motif } = covers[project];
  const p = { index };
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
