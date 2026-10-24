import { Composition, Still } from "remotion";

import { Cover } from "./Cover";
import { Promo, PROMO_FRAMES } from "./Promo";
import type { ProjectId } from "./projects";
import { FPS } from "./theme";

const ids: ProjectId[] = ["fridge-alert-bot", "hotel-ai-concierge", "uptime-monitor"];

export function RemotionRoot() {
  return (
    <>
      {ids.map((id) => (
        <Composition
          key={`promo-${id}`}
          id={`promo-${id}`}
          component={Promo}
          defaultProps={{ project: id }}
          durationInFrames={PROMO_FRAMES}
          fps={FPS}
          width={1920}
          height={1080}
        />
      ))}
      {ids.map((id) => (
        <Still
          key={`cover-${id}`}
          id={`cover-${id}`}
          component={Cover}
          defaultProps={{ project: id }}
          width={1920}
          height={1200}
        />
      ))}
    </>
  );
}
