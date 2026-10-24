import { AbsoluteFill, Sequence } from "remotion";

import { Appear, Label, RiseWords, Scene, TopRule } from "./components";
import { projects, type ProjectId } from "./projects";
import { ConciergeScreen, FridgeScreen, UptimeScreen } from "./scenes/screens";
import { colors, mono } from "./theme";

// Scene lengths in frames (30 fps): 5 s title, 8 s problem, 16 s screens, 8 s result, 5 s outro.
export const SCENES = { title: 150, problem: 240, screens: 480, result: 240, outro: 150 };
export const PROMO_FRAMES = Object.values(SCENES).reduce((a, b) => a + b, 0);
export const SCREENS_START = SCENES.title + SCENES.problem;

const screens: Record<ProjectId, () => JSX.Element> = {
  "fridge-alert-bot": FridgeScreen,
  "hotel-ai-concierge": ConciergeScreen,
  "uptime-monitor": UptimeScreen,
};

export function Promo({ project }: { project: ProjectId }) {
  const p = projects[project];
  const Screen = screens[project];
  let from = 0;
  const at = (length: number) => {
    const start = from;
    from += length;
    return { from: start, durationInFrames: length };
  };

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <Sequence {...at(SCENES.title)}>
        <Scene duration={SCENES.title}>
          <TopRule left={`Project ${p.index}`} right="Daniil Dushin" />
          <div style={{ marginTop: "auto" }}>
            <RiseWords text={p.title} size={190} start={8} stagger={3} />
            <Appear start={30}>
              <div style={{ marginTop: 34, fontSize: 44, color: colors.muted, maxWidth: 1300 }}>
                {p.summary}
              </div>
            </Appear>
          </div>
        </Scene>
      </Sequence>

      <Sequence {...at(SCENES.problem)}>
        <Scene duration={SCENES.problem}>
          <TopRule left="The problem" right={p.index} />
          <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
            {p.problem.map((line, i) => (
              <RiseWords key={line} text={line} size={104} start={8 + i * 34} />
            ))}
          </div>
        </Scene>
      </Sequence>

      <Sequence {...at(SCENES.screens)}>
        <Scene duration={SCENES.screens}>
          <TopRule left="How it works" right={p.index} />
          <Screen />
        </Scene>
      </Sequence>

      <Sequence {...at(SCENES.result)}>
        <Scene duration={SCENES.result}>
          <TopRule left="Result" right={p.index} />
          <div style={{ marginTop: 80, display: "flex", flexDirection: "column" }}>
            {p.result.map((line, i) => (
              <Appear key={line} start={10 + i * 22}>
                <div
                  style={{
                    display: "flex",
                    gap: 40,
                    alignItems: "baseline",
                    borderTop: `1px solid ${colors.line}`,
                    padding: "26px 0",
                    fontSize: 50,
                    fontWeight: 600,
                    letterSpacing: "-0.03em",
                  }}
                >
                  <span style={{ fontFamily: mono, fontSize: 24, color: colors.muted, fontWeight: 400 }}>
                    0{i + 1}
                  </span>
                  {line}
                </div>
              </Appear>
            ))}
          </div>
          <Appear start={110} style={{ marginTop: "auto" }}>
            <Label>{p.stack.join("  /  ")}</Label>
          </Appear>
        </Scene>
      </Sequence>

      <Sequence {...at(SCENES.outro)}>
        <Scene duration={SCENES.outro}>
          <TopRule left={p.title} />
          <div style={{ marginTop: "auto" }}>
            <RiseWords text="Daniil Dushin" size={170} start={6} />
            <Appear start={24}>
              <div style={{ marginTop: 26, fontSize: 44, color: colors.muted }}>
                AI Developer & IT/Network Technician · Antalya
              </div>
            </Appear>
          </div>
        </Scene>
      </Sequence>
    </AbsoluteFill>
  );
}
