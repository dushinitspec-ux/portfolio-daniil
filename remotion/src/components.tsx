import type { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { colors, mono, sans } from "./theme";

const ease = (t: number) => 1 - Math.pow(1 - t, 3);

/** Fades a whole scene in at the start and out at the end of its Sequence. */
export function Scene({ duration, children }: { duration: number; children: ReactNode }) {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10, duration - 10, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.bg,
        color: colors.fg,
        fontFamily: sans,
        padding: "100px 130px",
        opacity,
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        fontFamily: mono,
        fontSize: 26,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: colors.muted,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** The top rule of every scene: a label on the left and an accent square on the right. */
export function TopRule({ left, right }: { left: string; right?: string }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        borderBottom: `1px solid ${colors.line}`,
        paddingBottom: 22,
      }}
    >
      <Label>{left}</Label>
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        {right && <Label>{right}</Label>}
        <div style={{ width: 18, height: 18, background: colors.accent }} />
      </div>
    </div>
  );
}

/** Words rise one by one from behind a mask, like the headline on the website. */
export function RiseWords({
  text,
  start = 0,
  size,
  stagger = 2,
  weight = 600,
  style,
}: {
  text: string;
  start?: number;
  size: number;
  stagger?: number;
  weight?: number;
  style?: CSSProperties;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div
      style={{
        fontSize: size,
        fontWeight: weight,
        lineHeight: 1.02,
        letterSpacing: "-0.045em",
        ...style,
      }}
    >
      {text.split(" ").map((word, i) => {
        const progress = spring({
          frame: frame - start - i * stagger,
          fps,
          config: { damping: 200 },
          durationInFrames: 22,
        });
        return (
          <span key={i} style={{ display: "inline-block", overflow: "hidden", verticalAlign: "top", paddingBottom: "0.08em" }}>
            <span
              style={{
                display: "inline-block",
                transform: `translateY(${(1 - progress) * 110}%)`,
                color: word === "—" ? colors.accent : undefined,
              }}
            >
              {word}
            </span>
            {" "}
          </span>
        );
      })}
    </div>
  );
}

/** Fade and rise in at `start` (frames from the start of the scene). */
export function Appear({
  start,
  children,
  distance = 30,
  style,
}: {
  start: number;
  children: ReactNode;
  distance?: number;
  style?: CSSProperties;
}) {
  const frame = useCurrentFrame();
  const t = ease(interpolate(frame - start, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <div style={{ opacity: t, transform: `translateY(${(1 - t) * distance}px)`, ...style }}>
      {children}
    </div>
  );
}

/** A chat message. Guest messages sit on the right, like in Telegram. */
export function Bubble({
  start,
  side,
  text,
  tag,
  tone = "plain",
}: {
  start: number;
  side: "left" | "right";
  text: string;
  tag?: string;
  tone?: "plain" | "dark" | "alert" | "ok";
}) {
  const border = tone === "alert" ? colors.accent : tone === "ok" ? colors.green : colors.line;
  return (
    <Appear start={start} distance={20} style={{ display: "flex", justifyContent: side === "right" ? "flex-end" : "flex-start" }}>
      <div
        style={{
          maxWidth: "88%",
          background: tone === "dark" ? colors.fg : "#FFFFFF",
          color: tone === "dark" ? colors.bg : colors.fg,
          border: `1px solid ${border}`,
          borderLeft: tone === "alert" || tone === "ok" ? `6px solid ${border}` : undefined,
          padding: "18px 24px",
          fontSize: 28,
          lineHeight: 1.35,
          whiteSpace: "pre-line",
        }}
      >
        {tag && (
          <div style={{ fontFamily: mono, fontSize: 18, letterSpacing: "0.04em", opacity: 0.6, marginBottom: 6 }}>
            {tag}
          </div>
        )}
        {text}
      </div>
    </Appear>
  );
}

/** A screenshot that slides up inside its frame (the "reveal mask" used on the website). */
export function MaskedImage({ src, start, width, height }: { src: string; start: number; width: number; height: number }) {
  const frame = useCurrentFrame();
  const t = ease(interpolate(frame - start, [0, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <div style={{ width, height, overflow: "hidden", border: `1px solid ${colors.line}`, background: colors.surface }}>
      {/* <Img> makes the renderer wait until the picture has loaded before taking the frame. */}
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "top",
          transform: `translateY(${(1 - t) * 100}%) scale(${1.1 - t * 0.1})`,
        }}
      />
    </div>
  );
}
