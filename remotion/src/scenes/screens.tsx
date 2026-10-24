import { staticFile } from "remotion";

import { Appear, Bubble, Label, MaskedImage } from "../components";
import { colors, mono } from "../theme";

// The "UI screens" part of each promo. Texts are copied from real output of the projects.

function Column({ title, children, width }: { title: string; children: React.ReactNode; width: number }) {
  return (
    <div style={{ width, display: "flex", flexDirection: "column", gap: 18 }}>
      <Label style={{ borderBottom: `1px solid ${colors.line}`, paddingBottom: 14 }}>{title}</Label>
      {children}
    </div>
  );
}

export function FridgeScreen() {
  return (
    <div style={{ display: "flex", gap: 70, marginTop: 70, alignItems: "flex-start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <MaskedImage src={staticFile("fridge-history-chart.png")} start={8} width={1000} height={500} />
        <Appear start={30}>
          <Label>/history kitchen-fridge-1 · chart from the demo</Label>
        </Appear>
      </div>
      <Column title="Telegram · kitchen group" width={530}>
        <Bubble
          start={110}
          side="left"
          tone="alert"
          text={"🚨 Fridge alert: kitchen-fridge-1\nTemperature: 5.6 °C (limit 5.0 °C)\nAbove the limit for 1 min (since 14:17)."}
        />
        <Bubble
          start={270}
          side="left"
          tone="ok"
          text={"✅ Back to normal: fridge-1\nTemperature: 4.0 °C (limit 5.0 °C)\nThe incident lasted 11 min, peak 8.5 °C."}
        />
      </Column>
    </div>
  );
}

export function ConciergeScreen() {
  return (
    <div style={{ display: "flex", gap: 70, marginTop: 56 }}>
      <Column title="Guest · private chat" width={900}>
        <Bubble start={10} side="right" tag="RU" text="Какой пароль от вайфая?" />
        <Bubble
          start={40}
          side="left"
          text={"Из справочника отеля (Wi-Fi, текст на английском): Free Wi-Fi in all rooms and public areas. Network: LaraBreeze_Guest. The password is printed on the room key card holder."}
        />
        <Bubble start={120} side="right" tag="RU" text="Можно заказать торт на день рождения в номер?" />
        <Bubble
          start={150}
          side="left"
          text="У меня нет этой информации, поэтому я передал ваш вопрос на ресепшен."
        />
        <Bubble
          start={360}
          side="left"
          tone="ok"
          text={"💬 Ответ ресепшена:\nYes, our pastry chef can make a cake. Please order it at the reception a day before."}
        />
      </Column>
      <Column title="Staff · Telegram group" width={700}>
        <Bubble
          start={190}
          side="left"
          tone="alert"
          text={"❓ Question #1 from Иван Петров (@ivan) · Russian\nReason: not in the knowledge base\n\nМожно заказать торт на день рождения в номер?"}
        />
        <Bubble
          start={270}
          side="right"
          tone="dark"
          tag="REPLY"
          text="Yes, our pastry chef can make a cake. Please order it at the reception a day before."
        />
        <Bubble start={390} side="left" text="✅ Sent to the guest (question #1)" />
      </Column>
    </div>
  );
}

export function UptimeScreen() {
  return (
    <div style={{ display: "flex", gap: 70, marginTop: 70, alignItems: "flex-start" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <MaskedImage src={staticFile("uptime-status-page.jpg")} start={8} width={880} height={660} />
        <Appear start={30}>
          <Label>Status page · demo mode</Label>
        </Appear>
      </div>
      <Column title="Telegram · alerts" width={640}>
        <Bubble
          start={120}
          side="left"
          tone="alert"
          text={"🔴 Wi-Fi access point, lobby is DOWN (192.0.2.30)\nping: no reply\nNot responding since 14:37."}
        />
        <Bubble
          start={280}
          side="left"
          tone="ok"
          text={"🟢 Wi-Fi access point, lobby is back UP (192.0.2.30)\nDowntime: 24 s (14:37 - 14:38)."}
        />
        <Appear start={330}>
          <div style={{ fontFamily: mono, fontSize: 22, color: colors.muted, lineHeight: 1.5 }}>
            DOWN after 2 failed rounds · UP after 2 good ones
          </div>
        </Appear>
      </Column>
    </div>
  );
}
