// Uptime Monitor in the browser: the project's Monitor round, UP/DOWN state machine, alert
// texts, demo devices, generated history and status-page rows run in Python
// (app/web_demo.py). This file only draws what Python returns and passes on the clicks.
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: strings[lang]?.title ?? strings.en.title, strings });
const { t } = demo;
const py = await demo.python();

const ROUND_MS = 1500; // one simulated check round every 1.5 s of real time
const CAMERA = "Lobby camera";

// Python calls run one at a time, in the order they were made.
let queue = Promise.resolve();
function call(name, ...args) {
  const job = queue.then(() => py.call(name, ...args));
  queue = job.catch(() => {});
  return job;
}

function duration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return t("dSec", { s });
  const m = Math.floor(s / 60);
  if (m >= 60) return t("dHourMin", { h: Math.floor(m / 60), m: m % 60 });
  return s % 60 ? t("dMinSec", { m, s: s % 60 }) : t("dMin", { m });
}

const startedLabel = (unix) => {
  const date = new Date(unix * 1000);
  return `${date.toLocaleDateString(lang, { day: "numeric", month: "short", timeZone: "UTC" })} ${date.toISOString().slice(11, 16)}`;
};

let ui = {};
let snap = null;
let generation = 0;
let timer = null;
let running = false;
let live = false;
const rowNodes = new Map();

function narrate(text) {
  ui.caption.replaceChildren(el("span", { class: "d-enter", text }));
}

function vars() {
  const { rules } = snap;
  return {
    need: rules.fail_after,
    days: rules.history_days,
    count: snap.total,
    round: duration(rules.round_s),
    real: t("dSec", { s: (ROUND_MS / 1000).toLocaleString(lang) }),
  };
}

// A reply that arrives after Replay belongs to the previous run: drop it.
async function update(name, ...args) {
  const mine = generation;
  const next = await call(name, ...args);
  if (mine !== generation) return snap;
  render(next);
  return next;
}

const step = () => update("step", 1);
const setPlugged = (name, plugged) => update("set_plugged", name, plugged);

// Rendering

function deviceRow(name) {
  const parts = {
    name: el("span", { class: "um-name", text: name }),
    status: el("span", { class: "d-badge" }),
    sub: el("span", { class: "um-sub" }),
    uptime: el("span", { class: "um-uptime" }),
    bars: el("span", { class: "um-bars", role: "img" }),
    recent: el("span", { class: "um-recent", "aria-hidden": "true" }),
    state: el("span", { class: "um-state" }),
    problems: el("span", { class: "um-problems" }),
    button: el("button", { class: "d-btn um-plug", type: "button" }),
  };
  const node = el(
    "li",
    { class: "um-device" },
    el("div", { class: "um-line" }, parts.name, parts.status),
    el("div", { class: "um-line" }, parts.sub, parts.uptime),
    parts.bars,
    el("div", { class: "um-line" }, el("span", { class: "um-checks" }, el("span", { class: "d-label", text: t("lastChecks") }), parts.recent), parts.button),
    el("div", { class: "um-notes" }, parts.state, parts.problems),
  );
  // The whole row is a click target; the button inside is the keyboard one (clicks bubble).
  node.addEventListener("click", () => {
    if (!live || parts.button.disabled) return;
    const row = snap.rows.find((r) => r.name === name);
    setPlugged(name, row.unplugged);
  });
  rowNodes.set(name, parts);
  return node;
}

function renderRow(row) {
  const parts = rowNodes.get(row.name);
  parts.status.className = `d-badge ${row.status === "up" ? "ok" : row.status === "down" ? "fail" : "sim"}`;
  parts.status.textContent = row.status.toUpperCase();
  parts.sub.textContent = `${row.ip} · ${row.checks}${row.latency !== "—" ? ` · ${row.latency}` : ""}`;
  parts.uptime.textContent = `${t("h24")} ${row.uptime_24h} · ${t("d7")} ${row.uptime_7d}`;

  parts.bars.setAttribute("aria-label", t("barsLabel"));
  if (parts.bars.childElementCount !== row.bars.length) {
    parts.bars.replaceChildren(...row.bars.map(() => el("span")));
  }
  row.bars.forEach((bar, i) => {
    const node = parts.bars.children[i];
    node.className = `um-bar ${bar.level}`;
    node.title = t("barTitle", { hour: bar.hour, value: bar.uptime === null ? t("noData") : `${bar.uptime}%` });
  });

  parts.recent.replaceChildren(...row.recent.map((ok) => el("span", { class: ok ? "ok" : "fail" })));

  let state = "";
  if (row.status === "up" && row.failures > 0) state = t("failedRow", { n: row.failures, need: snap.rules.fail_after });
  if (row.status === "down") {
    state = t("downFor", { d: duration(row.down_for_s) });
    if (row.successes > 0) state += ` · ${t("goodRow", { n: row.successes, need: snap.rules.recover_after })}`;
  }
  parts.state.textContent = state;
  parts.problems.textContent = row.problems;

  parts.button.textContent = t(row.unplugged ? "plugIn" : "unplug");
  parts.button.setAttribute("aria-pressed", String(row.unplugged));
  parts.button.setAttribute("aria-label", t(row.unplugged ? "plugAria" : "unplugAria", { device: row.name }));
  parts.button.closest(".um-device").dataset.status = row.status;
  parts.button.closest(".um-device").classList.toggle("unplugged", row.unplugged);
}

function addAlert(message) {
  ui.chatEmpty?.remove();
  ui.chatEmpty = null;
  ui.chat.append(el("div", { class: "d-msg in d-enter d-flash" }, message.text, el("span", { class: "meta", text: message.clock })));
  ui.chat.scrollTop = ui.chat.scrollHeight;
}

function render(next) {
  snap = next;
  ui.summary.textContent = snap.down
    ? t("summaryDown", { down: snap.down, total: snap.total })
    : t("summaryUp", { up: snap.up, total: snap.total });
  ui.summary.className = `d-badge ${snap.down ? "fail" : "ok"}`;
  ui.clock.textContent = t("simTime", { time: snap.time });
  for (const row of snap.rows) renderRow(row);

  ui.outages.replaceChildren(
    ...snap.incidents.slice(0, 5).map((incident) =>
      el(
        "li",
        {},
        el("time", { text: startedLabel(incident.started_ts) }),
        el(
          "div",
          {},
          el("strong", { text: incident.device }),
          " · ",
          incident.duration_s === null ? el("span", { class: "um-ongoing", text: t("ongoing") }) : duration(incident.duration_s),
          el("div", { class: "um-sub", text: incident.problems }),
        ),
      ),
    ),
  );
  for (const message of snap.messages) addAlert(message);
}

// Rounds keep running after the autoplay, until the visitor pauses them or hides the page.
function runRounds() {
  clearTimeout(timer);
  const mine = generation;
  const tick = async () => {
    if (mine !== generation || !running) return;
    if (!document.hidden) {
      try {
        await step();
      } catch (error) {
        console.error(error);
      }
    }
    if (mine === generation && running) timer = setTimeout(tick, ROUND_MS);
  };
  timer = setTimeout(tick, ROUND_MS);
}

function setRunning(value) {
  running = value;
  ui.run.textContent = t(running ? "pause" : "run");
  ui.run.setAttribute("aria-pressed", String(running));
  if (running) runRounds();
  else clearTimeout(timer);
}

function setControls(enabled) {
  for (const node of [ui.next, ui.run, ...[...rowNodes.values()].map((p) => p.button)]) node.disabled = !enabled;
}

function build() {
  rowNodes.clear();
  ui.caption = el("p", { class: "um-narration", "aria-live": "polite" });
  ui.summary = el("span", { class: "d-badge" });
  ui.clock = el("span", { class: "d-note mono" });
  ui.devices = el("ul", { class: "um-devices" }, snap.rows.map((row) => deviceRow(row.name)));
  ui.next = el("button", { class: "d-btn", type: "button", text: t("nextRound"), onclick: () => step() });
  ui.run = el("button", { class: "d-btn solid", type: "button", text: t("run"), "aria-pressed": "false", onclick: () => setRunning(!running) });
  ui.outages = el("ol", { class: "d-log um-outages" });
  ui.chat = el("div", { class: "d-chat", role: "log", "aria-live": "polite" });
  ui.chatEmpty = el("p", { class: "um-chat-note", text: t("chatEmpty") });
  ui.chat.append(ui.chatEmpty);

  const status = el(
    "section",
    { class: "d-panel d-stack" },
    el(
      "div",
      { class: "um-head" },
      el("h2", { class: "d-title", text: t("statusTitle") }),
      el("div", { class: "d-row" }, ui.summary, el("span", { class: "d-badge sim", text: t("simulated") })),
    ),
    ui.clock,
    ui.devices,
    el("div", { class: "d-row" }, ui.next, ui.run),
    el("p", { class: "d-note", text: t("roundNote", vars()) }),
  );
  const side = el(
    "div",
    { class: "d-stack um-side" },
    el(
      "div",
      { class: "d-phone" },
      el(
        "div",
        { class: "d-phone-head" },
        el("span", { class: "d-avatar", "aria-hidden": "true", text: "UM" }),
        el("div", {}, el("div", { class: "name", text: "Uptime Monitor" }), el("div", { class: "sub", text: t("chatSub") })),
      ),
      ui.chat,
    ),
    el("p", { class: "d-note", text: t("alertsEnglish") }),
    el("section", { class: "d-panel" }, el("span", { class: "d-label", text: t("outages") }), ui.outages),
  );
  demo.stage.replaceChildren(ui.caption, el("div", { class: "d-cols wide-left" }, status, side));
}

function press(name) {
  const button = rowNodes.get(name).button;
  button.classList.remove("d-flash");
  void button.offsetWidth;
  button.classList.add("d-flash", "um-pressed");
  setTimeout(() => button.classList.remove("um-pressed"), 600);
}

async function rounds(play, count) {
  for (let i = 0; i < count; i += 1) {
    await play.wait(ROUND_MS);
    await step();
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && live && running) runRounds();
});

demo.autoplay({
  async reset() {
    generation += 1;
    clearTimeout(timer);
    live = false;
    running = false;
    demo.stage.replaceChildren(el("p", { class: "d-note um-preparing", text: t("preparing") }));
    snap = await call("start", 5);
    build();
    render(snap);
    setControls(false);
    narrate(t("capStart", vars()));
  },

  async script(play) {
    await rounds(play, 2);

    narrate(t("capMiss", vars()));
    press(CAMERA);
    await setPlugged(CAMERA, false);
    await rounds(play, 1);
    narrate(t("capOneMiss", vars()));
    await play.wait(1800);

    press(CAMERA);
    await setPlugged(CAMERA, true);
    await rounds(play, 1);
    narrate(t("capBack", vars()));
    await rounds(play, 1);

    narrate(t("capOffline", vars()));
    press(CAMERA);
    await setPlugged(CAMERA, false);
    await rounds(play, snap.rules.fail_after);
    narrate(t("capDown", vars()));
    await play.wait(1800);
    await rounds(play, 2);

    narrate(t("capPlug", vars()));
    press(CAMERA);
    await setPlugged(CAMERA, true);
    await rounds(play, 1);
    narrate(t("capOneGood", vars()));
    await play.wait(1800);
    await rounds(play, snap.rules.recover_after - 1);
    narrate(t("capUp", vars()));
    await play.wait(2000);
  },

  interactive() {
    live = true;
    setControls(true);
    narrate(t("capYourTurn", vars()));
    setRunning(true);
  },
});
