// Energy saver in the browser: real DE-LU day-ahead prices (the project's bundled
// Energy-Charts file) planned by the project's own planner in Python
// (projects/09-energy-saver/app/web_demo.py). Prices, plan, costs, savings and the DST
// labels all come from py.call(...); this file only draws them (inline SVG, no libraries).
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: strings[lang]?.title ?? strings.en.title, strings });
const { t } = demo;
const py = await demo.python();

const FEATURED_DAY = "2026-10-22"; // the day of the README screenshot; any listed day works
const SVG = "http://www.w3.org/2000/svg";
const money = new Intl.NumberFormat(lang, { style: "currency", currency: "EUR" });
const decimal = new Intl.NumberFormat(lang, { maximumFractionDigits: 2 });
const oneDecimal = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dayFormat = new Intl.DateTimeFormat(lang, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const longDayFormat = new Intl.DateTimeFormat(lang, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

let ui = null;
let info = null; // init(): prices, licence, days, devices.yaml
let site = null; // the devices and cap being planned (editable copy)
let live = false;
let view = null; // what the chart shows: { plan, upto, shown: Set|null, pending }
let seq = 0;

// --- Helpers ----------------------------------------------------------------------------

const euro = (text) => (text === null || text === undefined ? "—" : money.format(Number(text)));
const deviceName = (name) => {
  const key = `dev_${name}`;
  const text = t(key);
  return text === key ? name : text;
};
const dayLabel = (iso, long = false) => (long ? longDayFormat : dayFormat).format(new Date(`${iso}T12:00:00Z`));
const hoursLabel = (minutes) => t("hoursShort", { h: decimal.format(minutes / 60) });
const powerLabel = (kw) => t("kw", { v: decimal.format(Number(kw)) });
const clone = (value) => JSON.parse(JSON.stringify(value));

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  for (const child of children.flat()) if (child) node.append(child);
  return node;
}
function svgText(attrs, text) {
  const node = svg("text", attrs);
  node.textContent = text;
  return node;
}

function niceStep(span, ticks) {
  const raw = span / Math.max(ticks, 1);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  for (const factor of [1, 2, 2.5, 5, 10]) if (raw <= factor * magnitude) return factor * magnitude;
  return 10 * magnitude;
}

function timeOptions(fromMinutes, toMinutes) {
  const out = [];
  for (let m = fromMinutes; m <= toMinutes; m += 30) {
    out.push(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
  }
  return out;
}

function field(label, control, id) {
  return el("div", { class: "d-field" }, el("label", { class: "d-label", for: id, text: label }), control);
}

function selectOf(id, values, labelOf = (v) => v) {
  return el("select", { class: "d-select", id, disabled: true }, values.map((v) => el("option", { value: v, text: labelOf(v) })));
}

function showError(error) {
  console.error(error);
  ui.errors.replaceChildren(el("p", { class: "d-note es-error", text: t("pythonError", { message: String(error?.message ?? error).split("\n").slice(-2).join(" ") }) }));
}

// --- Layout -----------------------------------------------------------------------------

function build() {
  const daySelect = el(
    "select",
    { class: "d-select", id: "es-day", disabled: true },
    info.days.map((d) =>
      el("option", { value: d.day, text: t(d.hours === 25 ? "dayOption25" : d.hours === 23 ? "dayOption23" : "dayOption", { day: dayLabel(d.day) }) }),
    ),
  );
  const capInput = el("input", { class: "d-input", id: "es-cap", type: "number", min: "0.5", step: "0.5", inputmode: "decimal", placeholder: t("capHint"), disabled: true });
  const resetButton = el("button", { class: "d-btn", type: "button", disabled: true, text: t("reset") });

  // Device editor
  const deviceSelect = el("select", { class: "d-select", id: "es-dev", disabled: true });
  const power = el("input", { class: "d-input", id: "es-power", type: "number", min: "0.1", step: "0.1", inputmode: "decimal", disabled: true });
  const runTime = el("input", { class: "d-input", id: "es-run", type: "number", min: "0.25", step: "0.25", inputmode: "decimal", disabled: true });
  const from = selectOf("es-from", timeOptions(0, 23 * 60 + 30));
  const to = selectOf("es-to", timeOptions(30, 24 * 60));
  const finish = selectOf("es-finish", ["", ...timeOptions(30, 24 * 60)], (v) => v || t("none"));
  const contiguous = el("input", { type: "checkbox", id: "es-contiguous", disabled: true });
  const minBlock = el("p", { class: "d-note" });

  ui = {
    daySelect, capInput, resetButton, deviceSelect, power, runTime, from, to, finish, contiguous, minBlock,
    dst: el("p", { class: "es-dst", hidden: true }),
    totals: el("div", { class: "es-totals" }),
    peak: el("p", { class: "d-note mono es-peak" }),
    chartTitle: el("span", { class: "d-label" }),
    legend: el("div", { class: "es-legend" }),
    chartBox: el("div", { class: "es-chart" }),
    tip: el("div", { class: "es-tip", hidden: true }),
    status: el("p", { class: "d-note es-now" }),
    tbody: el("tbody"),
    order: el("p", { class: "d-note" }),
    errors: el("div", { class: "d-stack" }),
    message: el("pre", { class: "es-pre" }),
    note: el("p", { class: "d-note" }),
  };
  ui.chartBox.append(ui.tip);

  const intro = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "d-row" }, el("span", { class: "d-badge ok", text: t("realPrices") }), el("span", { class: "mono es-zone", text: `${info.bidding_zone} · ${info.timezone}` }), el("span", { class: "d-badge sim", text: t("sampleDevices") })),
    el("p", { class: "d-note", text: t("intro", { downloaded: dayLabel(info.downloaded_at.slice(0, 10), true) }) }),
  );
  const controls = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "es-controls" }, field(t("day"), daySelect, "es-day"), field(t("cap"), capInput, "es-cap"), el("div", { class: "es-reset" }, resetButton)),
    ui.note,
  );
  const chart = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "es-head" }, ui.chartTitle, ui.status),
    ui.legend,
    ui.chartBox,
    el(
      "p",
      { class: "d-note es-source" },
      `${info.attribution} · ${info.bidding_zone} · ${t("downloadedOn", { date: dayLabel(info.downloaded_at.slice(0, 10)) })} · `,
      el("a", { href: "https://creativecommons.org/licenses/by/4.0/", target: "_blank", rel: "noopener", text: `${t("license")}: CC BY 4.0` }),
    ),
  );
  const table = el(
    "section",
    { class: "d-panel d-stack" },
    el("span", { class: "d-label", text: t("devicesTitle") }),
    el(
      "div",
      { class: "d-scroll" },
      el(
        "table",
        { class: "d-table es-table" },
        el("thead", {}, el("tr", {}, el("th", { text: t("colDevice") }), el("th", { text: t("colWindow") }), el("th", { text: t("colPlan") }), el("th", { class: "num", text: t("colCost") }), el("th", { class: "num", text: t("colSaving") }))),
        ui.tbody,
      ),
    ),
    ui.order,
    el("p", { class: "d-note", text: t("spotOnly") }),
  );
  const editor = el(
    "section",
    { class: "d-panel d-stack" },
    el("span", { class: "d-label", text: t("editTitle") }),
    field(t("device"), deviceSelect, "es-dev"),
    el("div", { class: "es-grid2" }, field(t("power"), power, "es-power"), field(t("runTime"), runTime, "es-run")),
    el("div", { class: "es-grid3" }, field(t("from"), from, "es-from"), field(t("to"), to, "es-to"), field(t("finish"), finish, "es-finish")),
    el("label", { class: "es-check", for: "es-contiguous" }, contiguous, el("span", { text: t("contiguous") })),
    minBlock,
    ui.errors,
    el("p", { class: "d-note", text: t("replanNote") }),
  );
  const message = el(
    "details",
    { class: "d-panel es-message" },
    el("summary", { class: "d-label", text: t("messageTitle") }),
    ui.message,
  );

  demo.stage.replaceChildren(intro, controls, ui.dst, el("div", { class: "es-totalbox" }, ui.totals, ui.peak), chart, el("div", { class: "d-cols wide-left" }, table, editor), message);

  daySelect.addEventListener("change", () => live && replan());
  capInput.addEventListener("input", () => {
    if (!live) return;
    site.power_cap_kw = capInput.value.trim();
    replanSoon();
  });
  resetButton.addEventListener("click", () => {
    site = clone(info.site);
    fillEditor(0);
    replan();
  });
  deviceSelect.addEventListener("change", () => fillEditor(Number(deviceSelect.value)));
  for (const control of [power, runTime]) control.addEventListener("input", () => live && editDevice());
  for (const control of [from, to, finish, contiguous]) control.addEventListener("change", () => live && editDevice());

  new ResizeObserver(() => draw()).observe(ui.chartBox);
  renderTotals(null);
}

function setControls(enabled) {
  for (const control of [ui.daySelect, ui.capInput, ui.resetButton, ui.deviceSelect, ui.power, ui.runTime, ui.from, ui.to, ui.finish, ui.contiguous]) control.disabled = !enabled;
}

function ensureOption(select, value) {
  if (value && ![...select.options].some((o) => o.value === value)) select.append(el("option", { value, text: value }));
}

function fillEditor(index) {
  const devices = site.devices;
  ui.deviceSelect.replaceChildren(...devices.map((d, i) => el("option", { value: i, text: deviceName(d.name) })));
  ui.deviceSelect.value = String(index);
  const d = devices[index];
  const [start, end] = d.window.replace("–", "-").split("-");
  ui.power.value = d.power_kw;
  ui.runTime.value = String(d.run_time / 60);
  for (const [select, value] of [[ui.from, start], [ui.to, end === "00:00" ? "24:00" : end], [ui.finish, d.latest_finish ?? ""]]) {
    ensureOption(select, value);
    select.value = value;
  }
  ui.contiguous.checked = d.contiguous;
  ui.minBlock.textContent = d.contiguous ? "" : t("minBlock", { min: d.min_block });
  ui.capInput.value = site.power_cap_kw ?? "";
}

function editDevice() {
  const d = site.devices[Number(ui.deviceSelect.value)];
  d.power_kw = ui.power.value.trim();
  const hours = Number(ui.runTime.value);
  d.run_time = Number.isFinite(hours) ? Math.round(hours * 60) : null;
  d.window = `${ui.from.value}-${ui.to.value}`;
  d.latest_finish = ui.finish.value || null;
  d.contiguous = ui.contiguous.checked;
  ui.minBlock.textContent = d.contiguous ? "" : t("minBlock", { min: d.min_block });
  replanSoon();
}

// --- Rendering --------------------------------------------------------------------------

function renderTotals(plan) {
  const tot = plan?.totals;
  const tile = (label, value, extra, hero = false) =>
    el("div", { class: `es-tile${hero ? " hero" : ""}` }, el("span", { class: "d-label", text: label }), el("span", { class: "es-value", text: value }), extra ? el("span", { class: "d-note", text: extra }) : null);
  ui.totals.replaceChildren(
    tile(t("totPlanned"), tot ? euro(tot.cost) : "—"),
    tile(t("totBaseline"), tot ? euro(tot.baseline) : "—", t("baselineHint")),
    tile(t("totSaving"), tot ? euro(tot.saving) : "—", null, true),
    tile(t("totPercent"), tot?.percent ? `${oneDecimal.format(Number(tot.percent))} %` : "—"),
  );
  ui.peak.hidden = !plan;
  ui.peak.textContent = plan
    ? plan.power_cap_kw
      ? t("peakCap", { peak: decimal.format(Number(plan.peak_kw)), cap: decimal.format(Number(plan.power_cap_kw)) })
      : t("peakNoCap", { peak: decimal.format(Number(plan.peak_kw)) })
    : "";
}

function renderDst(plan) {
  const key = plan.hours === 25 ? "dst25" : plan.hours === 23 ? "dst23" : null;
  ui.dst.hidden = !key;
  ui.dst.textContent = key ? t(key) : "";
}

function renderLegend() {
  const item = (cls, label) => el("span", { class: "es-key" }, el("i", { class: cls }), label);
  ui.legend.replaceChildren(item("k-price", t("legendPrice")), item("k-used", t("legendUsed")), item("k-window", t("legendWindow")), item("k-plan", t("legendPlan")), item("k-base", t("legendBaseline")));
}

function isShown(name) {
  return !view.shown || view.shown.has(name);
}

function tableRow(d) {
  const plan = d.planned ? d.blocks.map((b) => b.text).join(", ") : t(`problem_${d.problem}`);
  return el(
    "tr",
    { class: "d-enter" },
    el("td", {}, el("div", { class: "es-devname", text: deviceName(d.name) }), el("div", { class: "d-note mono", text: `${powerLabel(d.power_kw)} × ${hoursLabel(d.run_time)}` })),
    el("td", { class: "mono es-nowrap", "data-label": t("colWindow"), text: `${d.window_text[0]}–${d.window_text[1]}` }),
    el("td", { class: `mono es-plancell${d.planned ? "" : " es-problem"}`, "data-label": t("colPlan"), text: plan }),
    el("td", { class: "num" }, el("div", { text: euro(d.cost) }), d.planned ? el("div", { class: "d-note", text: t("instead", { base: euro(d.baseline_cost) }) }) : null),
    el("td", { class: "num es-saving", "data-label": t("colSaving"), text: euro(d.saving) }),
  );
}

function renderTable() {
  const plan = view.plan;
  ui.tbody.replaceChildren(...plan.devices.filter((d) => isShown(d.name)).map(tableRow));
  ui.order.textContent = t("orderNote", { order: plan.order.map(deviceName).join(" → ") });
}

function draw() {
  if (!view?.plan || !ui) return;
  const plan = view.plan;
  const width = Math.max(280, Math.floor(ui.chartBox.clientWidth));
  const narrow = width < 560;
  const left = narrow ? 34 : 172;
  const right = 6;
  const top = 28;
  const priceHeight = narrow ? 150 : 210;
  const axisHeight = 22;
  const rowHeight = narrow ? 32 : 28;
  const rowsTop = top + priceHeight + axisHeight + 10;
  const height = rowsTop + plan.devices.length * rowHeight + 6;
  const n = plan.slots.length;
  const step = (width - left - right) / n;
  const x = (i) => left + i * step;
  const ct = plan.slots.map((s) => Number(s.ct));

  let lo = Math.min(0, ...ct);
  let hi = Math.max(0.1, ...ct);
  const tick = niceStep(hi - lo, narrow ? 3 : 4);
  lo = Math.floor(lo / tick) * tick;
  hi = Math.ceil(hi / tick) * tick;
  const y = (v) => top + ((hi - v) / (hi - lo)) * priceHeight;

  const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, class: "es-svg", role: "img", "aria-label": `${t("chartTitle")} · ${dayLabel(plan.day, true)}` });
  const [dayStart, dayEnd] = plan.day_range;

  // The evening before the plan day (night windows start there), shaded.
  if (dayStart > 0) root.append(svg("rect", { x: left, y: top, width: x(dayStart) - left, height: height - top, class: "es-before" }));

  // Repeated hour of the autumn DST night: the ticks Python labelled with a zone name.
  const repeated = plan.ticks.filter((tk) => tk.label.includes(" "));
  if (repeated.length >= 2) {
    const after = plan.ticks.find((tk) => tk.i > repeated[repeated.length - 1].i);
    const x0 = x(repeated[0].i);
    const x1 = x(after ? after.i : repeated[repeated.length - 1].i + 4);
    root.append(svg("rect", { x: x0, y: top, width: x1 - x0, height: priceHeight, class: "es-repeat" }));
    root.append(svgText({ x: x0 + 4, y: top + 28, class: "es-tick es-repeat-label" }, t("repeated")));
  }

  // Price axis: hairline grid, ct/kWh labels.
  for (let v = lo; v <= hi + tick / 1000; v += tick) {
    const value = Math.abs(v) < tick / 1000 ? 0 : v;
    root.append(svg("line", { x1: left, x2: width - right, y1: y(value), y2: y(value), class: value === 0 ? "es-zero" : "es-grid" }));
    root.append(svgText({ x: left - 6, y: y(value) + 3.5, class: "es-tick", "text-anchor": "end" }, decimal.format(value)));
  }
  root.append(svgText({ x: narrow ? 0 : left - 6, y: 12, class: "es-tick", "text-anchor": narrow ? "start" : "end" }, t("unit")));

  // Price columns; the slots used by the planned runs shown so far in the accent.
  const used = new Set();
  for (const d of plan.devices) if (isShown(d.name)) for (const b of d.blocks) for (let i = b.from; i < b.to; i++) used.add(i);
  const gap = step >= 6 ? 2 : step >= 3 ? 1 : 0;
  const upto = Math.min(view.upto ?? n, n);
  for (let i = 0; i < upto; i++) {
    const y0 = y(0);
    const y1 = y(ct[i]);
    root.append(svg("rect", { x: x(i) + gap / 2, y: Math.min(y0, y1), width: Math.max(step - gap, 0.6), height: Math.max(Math.abs(y1 - y0), 1), class: used.has(i) ? "es-bar on" : "es-bar" }));
    // A strip under the axis too, so a used slot shows even when its price is about zero.
    if (used.has(i)) root.append(svg("rect", { x: x(i), y: top + priceHeight + 1, width: step, height: 3, class: "es-used" }));
  }

  // Time axis: local hours from Python (every 3 h, or 6 h on phones); midnight lines.
  const every = narrow ? 6 : 3;
  for (const tk of plan.ticks) {
    const tx = x(tk.i);
    if (tk.hour === 0) {
      root.append(svg("line", { x1: tx, x2: tx, y1: top - 14, y2: height, class: "es-midnight" }));
      root.append(svgText({ x: tx + 4, y: top - 4, class: "es-tick es-date" }, dayLabel(tk.date)));
    }
    if (tk.hour % every !== 0 || tk.label.includes(" ")) continue;
    root.append(svg("line", { x1: tx, x2: tx, y1: top + priceHeight, y2: top + priceHeight + 4, class: "es-axis" }));
    const anchor = tx - left < 14 ? "start" : width - right - tx < 14 ? "end" : "middle";
    root.append(svgText({ x: tx, y: top + priceHeight + 16, class: "es-tick", "text-anchor": anchor }, tk.label.slice(0, 5)));
  }
  root.append(svg("line", { x1: left, x2: width - right, y1: top + priceHeight, y2: top + priceHeight, class: "es-axis" }));

  // One row per device: allowed window, planned runs, the naive run underneath.
  plan.devices.forEach((d, r) => {
    const ry = rowsTop + r * rowHeight;
    const barY = narrow ? ry + 14 : ry + 5;
    const barH = narrow ? 11 : 13;
    const label = deviceName(d.name);
    root.append(
      narrow
        ? svgText({ x: left, y: ry + 10, class: "es-rowlabel" }, label)
        : svgText({ x: left - 10, y: barY + barH / 2 + 4, class: "es-rowlabel", "text-anchor": "end" }, label),
    );
    const showing = isShown(d.name) || view.pending === d.name;
    if (!showing) return;
    const [w0, w1] = d.window;
    root.append(svg("rect", { x: x(w0), y: barY, width: Math.max(x(w1) - x(w0), 1), height: barH, class: "es-window" }));
    if (!isShown(d.name)) return;
    for (const b of d.baseline) root.append(svg("rect", { x: x(b.from), y: barY + barH + 1.5, width: Math.max(x(b.to) - x(b.from), 1), height: 2, class: "es-base" }));
    for (const b of d.blocks) {
      const bx = x(b.from) + 0.5;
      root.append(svg("rect", { x: bx, y: barY + 2, width: Math.max(x(b.to) - bx - 0.5, 1), height: barH - 4, rx: 2, class: "es-plan" }));
    }
    if (!d.planned) root.append(svgText({ x: x(w0) + 4, y: barY + barH - 3, class: "es-tick es-problem" }, t(`problem_${d.problem}`)));
  });

  // Hover layer: one tooltip per 15-minute slot.
  const hover = svg("line", { x1: 0, x2: 0, y1: top, y2: height, class: "es-hover", visibility: "hidden" });
  const hit = svg("rect", { x: left, y: 0, width: width - left - right, height, fill: "transparent" });
  root.append(hover, hit);
  const move = (event) => {
    const box = root.getBoundingClientRect();
    const i = Math.floor((event.clientX - box.left - left) / step);
    if (i < 0 || i >= upto) return leave();
    const slot = plan.slots[i];
    const running = plan.devices.filter((d) => isShown(d.name) && d.blocks.some((b) => b.from <= i && i < b.to)).map((d) => deviceName(d.name));
    hover.setAttribute("x1", x(i) + step / 2);
    hover.setAttribute("x2", x(i) + step / 2);
    hover.setAttribute("visibility", "visible");
    ui.tip.replaceChildren(
      el("div", { class: "mono", text: `${slot.label} · ${decimal.format(Number(slot.ct))} ${t("unit")}` }),
      el("div", { class: "d-note", text: running.length ? t("tipRunning", { devices: running.join(", ") }) : t("tipIdle") }),
    );
    ui.tip.hidden = false;
    const tipWidth = ui.tip.offsetWidth;
    const px = Math.min(Math.max(x(i) + step / 2 - tipWidth / 2, 0), width - tipWidth);
    ui.tip.style.transform = `translate(${px}px, ${Math.max(y(ct[i]) - 58, 0)}px)`;
  };
  const leave = () => {
    hover.setAttribute("visibility", "hidden");
    ui.tip.hidden = true;
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerdown", move);
  hit.addEventListener("pointerleave", leave);

  ui.chartBox.querySelector("svg")?.remove();
  ui.chartBox.prepend(root);
  ui.chartTitle.textContent = `${t("chartTitle")} · ${dayLabel(plan.day, true)}`;
}

function showPlan(plan) {
  view = { plan, upto: null, shown: null, pending: null };
  renderDst(plan);
  renderTotals(plan);
  renderTable();
  ui.message.textContent = plan.message;
  ui.status.textContent = "";
  draw();
}

// --- Planning (always Python) -----------------------------------------------------------

function currentSite() {
  return { power_cap_kw: site.power_cap_kw ?? null, devices: site.devices };
}

async function replan() {
  const mine = ++seq;
  try {
    const plan = await py.call("plan", ui.daySelect.value, currentSite());
    if (mine !== seq) return; // a newer edit is already being planned
    if (!plan.ok) return showRuleErrors(plan.errors);
    ui.errors.replaceChildren();
    showPlan(plan);
  } catch (error) {
    showError(error);
  }
}

let timer = null;
function replanSoon() {
  clearTimeout(timer);
  timer = setTimeout(replan, 160);
}

function showRuleErrors(errors) {
  const labels = { power_kw: t("power"), run_time: t("runTime"), window: t("from"), latest_finish: t("finish"), power_cap_kw: t("cap") };
  ui.errors.replaceChildren(
    el(
      "div",
      { class: "es-errors d-enter" },
      el("p", { class: "d-note", text: t("errorsTitle") }),
      el(
        "ul",
        {},
        errors.map((e) => {
          const who = e.device !== null && e.device !== undefined ? deviceName(site.devices[e.device]?.name ?? "") : "";
          const what = e.field ? labels[e.field] ?? e.field : "";
          return el("li", { class: "mono", text: [who, what].filter(Boolean).join(" · ") + (who || what ? ": " : "") + e.message });
        }),
      ),
      el("p", { class: "d-note", text: t("lastValid") }),
    ),
  );
}

// --- Autoplay ---------------------------------------------------------------------------

demo.autoplay({
  async reset() {
    live = false;
    seq += 1;
    view = null;
    info = await py.call("init");
    site = clone(info.site);
    build();
    renderLegend();
    fillEditor(0);
  },

  async script(play) {
    const call = async (...args) => {
      const result = await py.call(...args);
      play.check(); // a Replay during the call: stop before drawing into the new run
      return result;
    };
    const days = info.days.map((d) => d.day);
    const featured = days.includes(FEATURED_DAY) ? FEATURED_DAY : days[days.length - 2];
    const dstDay = info.days.find((d) => d.hours !== 24)?.day;

    await play.wait(900);
    ui.daySelect.value = featured;
    ui.daySelect.classList.add("d-flash");
    await play.wait(700);

    // The 15-minute prices of the day, left to right.
    const plan = await call("plan", featured, currentSite());
    view = { plan, upto: 0, shown: new Set(), pending: null };
    renderDst(plan);
    ui.message.textContent = plan.message;
    renderTable();
    play.show(ui.chartBox);
    for (let upto = 0; upto <= plan.slots.length; upto += 6) {
      view.upto = upto;
      draw();
      await play.wait(60);
    }
    view.upto = null;
    draw();
    await play.wait(1200);

    // Each device in the order the planner takes them: window first, then the run.
    for (const name of plan.order) {
      view.pending = name;
      ui.status.textContent = t("planningNow", { name: deviceName(name) });
      draw();
      await play.wait(1100);
      view.shown.add(name);
      view.pending = null;
      draw();
      renderTable();
      await play.wait(1700);
    }
    ui.status.textContent = "";

    // Totals against the naive schedule.
    renderTotals(plan);
    ui.totals.classList.add("d-flash");
    play.show(ui.totals);
    await play.wait(4500);

    // The 25-hour day when the clocks go back.
    if (dstDay) {
      ui.daySelect.value = dstDay;
      ui.daySelect.classList.remove("d-flash");
      void ui.daySelect.offsetWidth;
      ui.daySelect.classList.add("d-flash");
      await play.wait(800);
      showPlan(await call("plan", dstDay, currentSite()));
      ui.dst.classList.add("d-flash");
      play.show(ui.dst);
      await play.wait(5000);
    }
  },

  interactive() {
    live = true;
    setControls(true);
    ui.note.textContent = t("yourTurn");
    if (view) {
      view = { ...view, upto: null, shown: null, pending: null };
      renderTable();
      draw();
    }
  },
});
