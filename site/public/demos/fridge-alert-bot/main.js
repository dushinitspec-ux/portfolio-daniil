// Fridge Alert Bot in the browser: the project's FridgeService, alert rules, fridge simulator
// and bot replies run in Python (app/web_demo.py). This file only draws what Python returns:
// the chart, the fridge state and the Telegram-like chat.
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: strings[lang]?.title ?? strings.en.title, strings });
const { t } = demo;
const py = await demo.python();

const TICK_MS = 500; // one 30 s reading step every half second: time runs ×60
const DOOR_TICKS = 6; // the scripted door stays open for 6 steps (3 simulated minutes)
const SVG = "http://www.w3.org/2000/svg";

// Python calls run one at a time, in the order they were made.
let queue = Promise.resolve();
function call(name, ...args) {
  const job = queue.then(() => py.call(name, ...args));
  queue = job.catch(() => {});
  return job;
}

// Formatting (display only; every value comes from Python)

const num = (value, digits = 1) =>
  Number(value).toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });

function duration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return t("dSec", { s });
  const m = Math.floor(s / 60);
  return s % 60 ? t("dMinSec", { m, s: s % 60 }) : t("dMin", { m });
}

const hhmm = (unix) => new Date(unix * 1000).toISOString().slice(11, 16);

/** The bot's Telegram HTML (<b>, <i>, <code> and entities) as DOM nodes; anything else stays text. */
function richText(html) {
  const root = document.createDocumentFragment();
  const stack = [root];
  const entities = { lt: "<", gt: ">", amp: "&", quot: '"', "#39": "'", "#x27": "'" };
  const pattern = /<(\/?)(b|i|code)>|&(lt|gt|amp|quot|#39|#x27);/g;
  let last = 0;
  const text = (value) => value && stack.at(-1).append(document.createTextNode(value));
  for (const match of html.matchAll(pattern)) {
    text(html.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[3]) text(entities[match[3]]);
    else if (match[1]) {
      if (stack.length > 1) stack.pop();
    } else {
      const node = document.createElement({ b: "strong", i: "em", code: "code" }[match[2]]);
      stack.at(-1).append(node);
      stack.push(node);
    }
  }
  text(html.slice(last));
  return root;
}

// Chart: an inline SVG drawn from the points Python returns

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== undefined) node.setAttribute(key, String(value));
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
}

let clipCount = 0;

function drawChart(box, { points, limit, from, to, height, sensor }) {
  const width = Math.max(240, Math.round(box.clientWidth || 600));
  const pad = { left: 34, right: 10, top: 10, bottom: 22 };
  const temps = points.map((p) => p[1]);
  let lo = Math.floor(Math.min(limit, ...temps) - 0.5);
  let hi = Math.ceil(Math.max(limit, ...temps) + 0.5);
  const stepY = hi - lo > 14 ? 5 : hi - lo > 7 ? 2 : 1;
  lo = Math.floor(lo / stepY) * stepY;
  hi = Math.ceil(hi / stepY) * stepY;
  const x = (ts) => pad.left + ((ts - from) / Math.max(1, to - from)) * (width - pad.left - pad.right);
  const y = (c) => pad.top + ((hi - c) / (hi - lo)) * (height - pad.top - pad.bottom);

  const grid = svg("g", { class: "fd-grid" });
  for (let c = lo; c <= hi; c += stepY) {
    grid.append(
      svg("line", { x1: pad.left, x2: width - pad.right, y1: y(c), y2: y(c) }),
      svg("text", { x: pad.left - 6, y: y(c) + 4, "text-anchor": "end" }, String(c)),
    );
  }
  const minutes = (to - from) / 60;
  const stepX = [5, 10, 15, 30, 60, 120, 180, 360, 720, 1440].find((m) => minutes / m <= Math.max(2, Math.floor(width / 90))) ?? 1440;
  for (let ts = Math.ceil(from / (stepX * 60)) * stepX * 60; ts <= to; ts += stepX * 60) {
    grid.append(svg("text", { x: x(ts), y: height - 6, "text-anchor": "middle" }, hhmm(ts)));
  }

  const chart = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    width,
    height,
    class: "fd-chart",
    role: "img",
    "aria-label": t("chartTitle", { sensor, limit: num(limit) }),
  });
  chart.append(grid);
  if (points.length) {
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join("");
    const first = x(points[0][0]).toFixed(1);
    const end = x(points.at(-1)[0]).toFixed(1);
    const id = `fd-clip-${++clipCount}`;
    chart.append(
      svg("clipPath", { id }, svg("rect", { x: 0, y: 0, width, height: Math.max(0, y(limit)) })),
      svg("path", { class: "fd-above", d: `M${first} ${y(limit)}${line.replace(/^M/, "L")}L${end} ${y(limit)}Z`, "clip-path": `url(#${id})` }),
      svg("path", { class: "fd-line", d: line }),
      svg("circle", { class: "fd-dot", cx: end, cy: y(points.at(-1)[1]), r: 3.5 }),
    );
  }
  chart.append(
    svg("line", { class: "fd-limit", x1: pad.left, x2: width - pad.right, y1: y(limit), y2: y(limit) }),
    svg("text", { class: "fd-limit-label", x: pad.left + 6, y: y(limit) - 5 }, t("axisLimit", { limit: num(limit) })),
  );
  box.replaceChildren(chart);
}

// The page

let ui = {};
let snap = null;
let generation = 0;
let loopTimer = null;
let paused = false;
let live = false;

/** Text with the bot commands in it set in monospace, so "/history kitchen-fridge-1 1" reads right. */
function withCommands(text) {
  return text.split(/(\/(?:status|history|setlimit|report|help)(?: kitchen-fridge-1(?: \d+)?)?)/).map((part, i) =>
    i % 2 ? el("code", { class: "fd-cmd", text: part }) : part,
  );
}

function narrate(text) {
  ui.caption.replaceChildren(el("span", { class: "d-enter" }, withCommands(text)));
}

function vars() {
  const { rules, sensor } = snap;
  return {
    limit: num(sensor.limit),
    delay: duration(rules.delay_s),
    step: duration(rules.step_s),
    door: duration(DOOR_TICKS * rules.step_s),
    hyst: num(rules.hysteresis_c),
    recover: num(sensor.limit - rules.hysteresis_c),
  };
}

function scrollChat() {
  ui.chat.scrollTop = ui.chat.scrollHeight;
}

function addMessage(direction, content, clock, { flash = false } = {}) {
  const bubble = el("div", { class: `d-msg ${direction} d-enter${flash ? " d-flash" : ""}` }, content, el("span", { class: "meta", text: clock }));
  ui.chat.append(bubble);
  scrollChat();
  return bubble;
}

function addNote(text) {
  ui.chat.append(el("p", { class: "fd-chat-note d-enter" }, withCommands(text)));
  scrollChat();
}

function render(next) {
  snap = next;
  const { sensor, fridge, rules } = snap;
  ui.temp.textContent = `${num(sensor.temperature)} °C`;
  const badge = { ok: ["ok", "stateOk"], pending: ["warn", "statePending"], alert: ["fail", "stateAlert"] }[sensor.state];
  ui.state.className = `d-badge ${badge[0]}`;
  ui.state.textContent = t(badge[1]);
  const v = vars();
  ui.limit.textContent = t("limit", { limit: v.limit });
  ui.note.textContent =
    sensor.state === "pending"
      ? t("pendingNote", { above: duration(sensor.above_for_s), delay: v.delay })
      : sensor.state === "alert"
        ? t("alertNote", { above: duration(sensor.above_for_s), recover: v.recover })
        : t("okNote");
  ui.mode.textContent = t({ normal: "modeNormal", door_open: "modeDoor", failure: "modeFailure" }[fridge.mode]);
  ui.mode.dataset.mode = fridge.mode;
  ui.clock.textContent = t("simTime", { time: snap.time });
  drawChart(ui.chartBox, { points: snap.points, limit: sensor.limit, from: snap.now - 3600, to: snap.now, height: 220, sensor: sensor.id });

  ui.door.textContent = t(fridge.door_open ? "closeDoor" : "openDoor");
  ui.door.setAttribute("aria-pressed", String(fridge.door_open));
  ui.compressor.textContent = t(fridge.compressor_broken ? "repair" : "breakCompressor");
  ui.compressor.setAttribute("aria-pressed", String(fridge.compressor_broken));
  if (document.activeElement !== ui.limitInput) ui.limitInput.value = num(sensor.limit);

  for (const message of snap.messages) addMessage("in", richText(message.text), message.clock, { flash: true });
  return snap;
}

// A reply that arrives after Replay belongs to the previous run: drop it.
async function update(name, ...args) {
  const mine = generation;
  const next = await call(name, ...args);
  return mine === generation ? next : null;
}

async function tick() {
  const next = await update("advance", snap.rules.step_s);
  return next ? render(next) : snap;
}

async function send(text) {
  const message = text.trim();
  if (!message) return;
  addMessage("out", message, snap.clock);
  const reply = await update("command", message);
  if (!reply) return;
  if (reply.kind === "text") addMessage("in", richText(reply.text), reply.clock);
  else if (reply.kind === "chart") {
    const box = el("div", { class: "fd-photo" });
    addMessage("in", [box, el("span", { class: "fd-caption-text" }, richText(reply.caption))], reply.clock);
    const times = reply.points.map((p) => p[0]);
    drawChart(box, {
      points: reply.points,
      limit: reply.limit,
      from: Math.min(...times, reply.snapshot.now - 3600),
      to: reply.snapshot.now,
      height: 170,
      sensor: reply.sensor,
    });
    scrollChat();
  } else addNote(t("ignored"));
  render(reply.snapshot);
}

async function setDoor(open) {
  const next = await update("set_door", open);
  if (next) render(next);
}

async function setCompressor(broken) {
  const next = await update("set_compressor", broken);
  if (next) render(next);
}

function press(button) {
  button.classList.remove("d-flash");
  void button.offsetWidth;
  button.classList.add("d-flash", "fd-pressed");
  setTimeout(() => button.classList.remove("fd-pressed"), 600);
}

// Time keeps running after the autoplay, until the visitor pauses it or hides the page.
function runClock() {
  clearTimeout(loopTimer);
  const mine = generation;
  const step = async () => {
    if (mine !== generation || paused) return;
    if (!document.hidden) {
      try {
        await tick();
      } catch (error) {
        console.error(error);
      }
    }
    if (mine === generation && !paused) loopTimer = setTimeout(step, TICK_MS);
  };
  loopTimer = setTimeout(step, TICK_MS);
}

function setControls(enabled) {
  for (const node of [ui.door, ui.compressor, ui.limitInput, ui.limitButton, ui.pause, ui.input, ui.sendButton, ...ui.keys]) {
    node.disabled = !enabled;
  }
}

function build() {
  const sim = el("span", { class: "d-badge sim", text: t("simulated") });
  ui.temp = el("span", { class: "d-big" });
  ui.state = el("span", { class: "d-badge" });
  ui.limit = el("span");
  ui.note = el("span");
  ui.mode = el("p", { class: "fd-mode" });
  ui.clock = el("span", { class: "mono" });
  ui.chartBox = el("div", { class: "fd-chart-box" });
  ui.caption = el("p", { class: "fd-narration", "aria-live": "polite" });

  ui.door = el("button", { class: "d-btn", type: "button", "aria-pressed": "false" });
  ui.compressor = el("button", { class: "d-btn", type: "button", "aria-pressed": "false" });
  ui.pause = el("button", { class: "d-btn", type: "button", text: t("pause"), "aria-pressed": "false" });
  ui.limitInput = el("input", { class: "d-input", id: "fd-limit", type: "text", inputmode: "decimal", autocomplete: "off", spellcheck: "false" });
  ui.limitButton = el("button", { class: "d-btn", type: "submit", text: t("setLimit") });
  const limitForm = el(
    "form",
    { class: "fd-limit-form" },
    el("label", { class: "d-label", for: "fd-limit", text: t("limitField", { sensor: "kitchen-fridge-1" }) }),
    el("div", { class: "d-row" }, ui.limitInput, ui.limitButton),
  );

  ui.door.onclick = () => setDoor(!snap.fridge.door_open);
  ui.compressor.onclick = () => setCompressor(!snap.fridge.compressor_broken);
  ui.pause.onclick = () => {
    paused = !paused;
    ui.pause.textContent = t(paused ? "resume" : "pause");
    ui.pause.setAttribute("aria-pressed", String(paused));
    if (!paused && live) runClock();
  };
  limitForm.onsubmit = (event) => {
    event.preventDefault();
    send(`/setlimit ${snap.sensor.id} ${ui.limitInput.value}`);
  };

  ui.chat = el("div", { class: "d-chat", role: "log", "aria-live": "polite" });
  ui.input = el("input", { class: "d-input", id: "fd-message", type: "text", autocomplete: "off", spellcheck: "false", placeholder: "/status" });
  ui.sendButton = el("button", { class: "d-btn solid", type: "submit", text: t("send") });
  const composer = el(
    "form",
    { class: "d-composer" },
    el("label", { class: "fd-hidden", for: "fd-message", text: t("message") }),
    ui.input,
    ui.sendButton,
  );
  composer.onsubmit = (event) => {
    event.preventDefault();
    const text = ui.input.value;
    ui.input.value = "";
    send(text);
  };
  ui.keys = ["/status", "/history kitchen-fridge-1 1", "/report"].map((command) =>
    el("button", { class: "d-btn", type: "button", text: command, onclick: () => send(command) }),
  );

  const fridgePanel = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "fd-head" }, el("span", { class: "d-label", text: `${t("fridge")} · kitchen-fridge-1` }), sim),
    el("div", { class: "d-row fd-reading" }, ui.temp, ui.state),
    el("p", { class: "d-note" }, ui.limit, " · ", ui.note),
    ui.mode,
    el("span", { class: "d-label", text: t("chart") }),
    ui.chartBox,
    el("p", { class: "d-note" }, ui.clock, el("br"), t("speed")),
  );
  const controls = el(
    "section",
    { class: "d-panel d-stack" },
    el("span", { class: "d-label", text: t("controls") }),
    el("div", { class: "d-row" }, ui.door, ui.compressor, ui.pause),
    limitForm,
  );
  const phone = el(
    "section",
    { class: "fd-side d-stack" },
    el(
      "div",
      { class: "d-phone" },
      el(
        "div",
        { class: "d-phone-head" },
        el("span", { class: "d-avatar", "aria-hidden": "true", text: "FA" }),
        el("div", {}, el("div", { class: "name", text: "Fridge Alert Bot" }), el("div", { class: "sub", text: t("chatSub") })),
      ),
      ui.chat,
      el("div", { class: "fd-keys d-keys" }, ui.keys),
      composer,
    ),
    el("p", { class: "d-note", text: t("botEnglish") }),
  );
  demo.stage.replaceChildren(
    ui.caption,
    el("div", { class: "d-cols wide-left" }, el("div", { class: "d-stack" }, fridgePanel, controls), phone),
  );
}

async function ticks(play, count, onEach) {
  for (let i = 0; i < count; i += 1) {
    await play.wait(TICK_MS);
    const next = await tick();
    onEach?.(next);
  }
}

async function ticksUntil(play, done, max, onEach) {
  for (let i = 0; i < max; i += 1) {
    await play.wait(TICK_MS);
    const next = await tick();
    onEach?.(next);
    if (done(next)) return next;
  }
  return snap;
}

new ResizeObserver(() => {
  if (snap && ui.chartBox?.isConnected) drawChart(ui.chartBox, { points: snap.points, limit: snap.sensor.limit, from: snap.now - 3600, to: snap.now, height: 220, sensor: snap.sensor.id });
}).observe(document.getElementById("demo"));

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && live && !paused) runClock();
});

demo.autoplay({
  async reset() {
    generation += 1;
    clearTimeout(loopTimer);
    live = false;
    paused = false;
    build();
    setControls(false);
    render(await call("start", 7));
    addMessage("out", "/start", snap.clock);
    const help = await call("command", "/start");
    addMessage("in", richText(help.text), help.clock);
    narrate(t("capStart", vars()));
  },

  async script(play) {
    await ticks(play, 6);
    await play.wait(400);

    press(ui.door);
    await setDoor(true);
    narrate(t("capDoor", vars()));
    let said = false;
    await ticks(play, DOOR_TICKS, (s) => {
      if (s.sensor.state === "pending" && !said) {
        said = true;
        narrate(t("capPending", vars()));
      }
    });
    press(ui.door);
    await setDoor(false);
    await ticksUntil(play, (s) => s.sensor.state === "ok", 20);
    narrate(t("capNoAlert", vars()));
    await ticks(play, 4);
    await play.wait(800);

    press(ui.compressor);
    await setCompressor(true);
    narrate(t("capBroken", vars()));
    said = false;
    await ticksUntil(play, (s) => s.messages.length > 0, 80, (s) => {
      if (s.sensor.state === "pending" && !said) {
        said = true;
        narrate(t("capWaiting", vars()));
      }
    });
    narrate(t("capAlert", vars()));
    await play.wait(1500);
    await ticks(play, 5);

    press(ui.compressor);
    await setCompressor(false);
    narrate(t("capRepair", vars()));
    await ticksUntil(play, (s) => s.messages.length > 0, 80);
    narrate(t("capRecovered", vars()));
    await play.wait(2200);

    narrate(t("capStatus", vars()));
    await play.type(ui.input, "/status");
    await play.wait(300);
    ui.input.value = "";
    await send("/status");
    await play.wait(1200);
  },

  interactive() {
    setControls(true);
    narrate(t("capYourTurn", vars()));
    live = true;
    runClock();
  },
});
