// Network inventory in the browser: the project's simulated office, run through its real
// register code in Python (projects/07-network-inventory/app/web_demo.py). Every row,
// counter, change, risk and exported file on screen comes from py.call(...); this file only
// lays it out.
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: strings[lang]?.title ?? strings.en.title, strings });
const { t } = demo;
const py = await demo.python();

const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const dateFormat = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const numberFormat = new Intl.NumberFormat(lang);

let ui = null; // DOM of the current run
let live = false; // controls enabled (after the autoplay)
let busy = false;
let info = null; // start(): scope, hosts, vendors
let listing = null; // last scan()/devices() result shown in the table
let lastScan = null; // last scan() result: its changes and alert
let lastDetail = null;
let selectedId = null;
let blobUrl = null;

// --- Small helpers ----------------------------------------------------------------------

const when = (iso) => (iso ? dateFormat.format(new Date(iso)) : "—");
const portList = (ports) => ports.map((p) => (p.service ? `${p.port} ${p.service}` : String(p.port))).join(", ");
const vendorOf = (d) => (d.randomised ? t("randomised") : d.vendor ?? t("unknownVendor"));
const size = (n) => (n < 1024 ? `${n} B` : `${numberFormat.format(Math.round(n / 102.4) / 10)} KB`);

/** The rule texts are translated by risk code; English shows Python's own text. */
function ruleText(code, field, fallback) {
  const key = `risk_${code}_${field}`;
  const text = t(key);
  return text === key ? fallback : text;
}

function severityBadge(severity) {
  const tone = { high: "fail", medium: "warn", low: "ni-low" }[severity] ?? "";
  return el("span", { class: `d-badge ${tone}`, text: t(`sev_${severity}`) });
}

function statusBadges(d) {
  return [
    d.new ? el("span", { class: "d-badge solid", text: t("badgeNew") }) : null,
    d.present ? null : el("span", { class: "d-badge sim", text: t("badgeGone") }),
    d.known ? null : el("span", { class: "d-badge ni-low", text: t("badgeUnconfirmed") }),
  ];
}

function deviceButton(id, label) {
  return el("button", { class: "ni-dev", type: "button", disabled: !live, onclick: () => openDevice(id) }, label);
}

function selectField(id, label, options) {
  const select = el(
    "select",
    { class: "d-select", id, disabled: true },
    options.map(([value, key]) => el("option", { value, text: t(key) })),
  );
  return { select, field: el("div", { class: "d-field" }, el("label", { class: "d-label", for: id, text: label }), select) };
}

function filterArgs() {
  return [ui.search.value, ui.risk.value, ui.status.value];
}

const filtersActive = () => ui.search.value.trim() !== "" || ui.risk.value !== "all" || ui.status.value !== "all";

function showError(error) {
  console.error(error);
  ui.error.textContent = t("pythonError", { message: String(error?.message ?? error).split("\n").slice(-2).join(" ") });
  ui.error.hidden = false;
}

// --- Layout -----------------------------------------------------------------------------

function build() {
  const scanButton = el("button", { class: "d-btn solid", type: "button", disabled: true, onclick: () => runScan() }, t("runScan", { n: 1 }));
  const search = el("input", { class: "d-input", id: "ni-q", type: "search", autocomplete: "off", spellcheck: "false", placeholder: t("searchHint"), disabled: true });
  const risk = selectField("ni-risk", t("risk"), [["all", "riskAll"], ["any", "riskAny"], ["high", "riskHigh"], ["none", "riskNone"]]);
  const status = selectField("ni-status", t("status"), [
    ["all", "statusAll"], ["present", "statusPresent"], ["missing", "statusMissing"], ["new", "statusNew"], ["unknown", "statusUnknown"],
  ]);
  const csvButton = el("button", { class: "d-btn", type: "button", disabled: true, onclick: () => exportFile("csv", true) }, t("exportCsv"));
  const jsonButton = el("button", { class: "d-btn", type: "button", disabled: true, onclick: () => exportFile("json", true) }, t("exportJson"));

  let timer = null;
  search.addEventListener("input", () => {
    if (!live) return;
    clearTimeout(timer);
    timer = setTimeout(() => refresh(), 150);
  });
  for (const control of [risk.select, status.select]) control.addEventListener("change", () => live && refresh());

  const tbody = el("tbody");
  const table = el(
    "table",
    { class: "d-table ni-table" },
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { text: t("colIp") }),
        el("th", { class: "ni-wide", text: t("colMac") }),
        el("th", { class: "ni-wide", text: t("colVendor") }),
        el("th", { text: t("colDevice") }),
        el("th", { class: "ni-portcol", text: t("colPorts") }),
        el("th", { text: t("colRisk") }),
      ),
    ),
    tbody,
  );

  ui = {
    scanButton, search, risk: risk.select, status: status.select, csvButton, jsonButton, tbody,
    scanInfo: el("p", { class: "ni-scaninfo mono" }),
    note: el("p", { class: "d-note" }),
    error: el("p", { class: "d-note ni-error", hidden: true }),
    stats: el("div", { class: "ni-stats" }),
    count: el("span", { class: "d-label" }),
    tableBox: el("div", { class: "d-scroll" }, table),
    changesTitle: el("span", { class: "d-label" }),
    changes: el("div", { class: "d-stack" }),
    alert: el("div", { class: "d-stack" }),
    detail: el("div", { class: "d-stack" }),
    exportOut: el("div", { class: "d-stack" }),
  };

  const intro = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "d-row" }, el("span", { class: "d-badge sim", text: t("simOffice") }), el("span", { class: "mono ni-scope", text: t("scopeLine", { scope: info.scope, hosts: numberFormat.format(info.hosts) }) })),
    el("p", { class: "d-note", text: t("intro", { vendors: numberFormat.format(info.vendors) }) }),
  );
  const tools = el(
    "section",
    { class: "d-panel d-stack" },
    el("div", { class: "d-row ni-scanrow" }, scanButton, ui.scanInfo),
    ui.note,
    ui.error,
    el(
      "div",
      { class: "ni-filters" },
      el("div", { class: "d-field ni-search" }, el("label", { class: "d-label", for: "ni-q", text: t("search") }), search),
      risk.field,
      status.field,
    ),
  );
  const register = el(
    "section",
    { class: "d-panel" },
    el("div", { class: "ni-head" }, el("span", { class: "d-label", text: t("register") }), ui.count),
    ui.tableBox,
  );
  ui.changesPanel = el("section", { class: "d-panel d-stack" }, ui.changesTitle, ui.changes, ui.alert);
  ui.detailPanel = el("section", { class: "d-panel d-stack" }, el("span", { class: "d-label", text: t("detailTitle") }), ui.detail);
  ui.exportPanel = el(
    "section",
    { class: "d-panel d-stack" },
    el("span", { class: "d-label", text: t("exportTitle") }),
    el("p", { class: "d-note", text: t("exportNote") }),
    el("div", { class: "d-row" }, csvButton, jsonButton),
    ui.exportOut,
  );

  demo.stage.replaceChildren(intro, tools, ui.stats, register, el("div", { class: "d-cols" }, ui.changesPanel, ui.detailPanel), ui.exportPanel);
  renderScanInfo(null);
  renderSummary(null);
  renderTable([]);
  renderChanges(null);
  renderDetail(null);
}

// --- Rendering --------------------------------------------------------------------------

function renderScanInfo(scan) {
  ui.scanInfo.textContent = scan
    ? t("scanInfo", { id: scan.id, when: when(scan.finished_at), found: scan.devices_found })
    : t("noScan");
  if (!busy) ui.scanButton.textContent = t("runScan", { n: (scan?.id ?? 0) + 1 });
}

function renderSummary(summary) {
  const items = [["total", "sumTotal"], ["present", "sumPresent"], ["new", "sumNew"], ["gone", "sumGone"], ["unknown", "sumUnknown"], ["high", "sumHigh"]];
  ui.stats.replaceChildren(
    ...items.map(([key, label]) =>
      el("div", { class: `ni-stat${key === "high" && summary?.high ? " hot" : ""}` }, el("span", { class: "d-label", text: t(label) }), el("span", { class: "ni-value", text: summary ? numberFormat.format(summary[key]) : "—" })),
    ),
  );
}

function rowFor(d) {
  const risk = d.highest_risk
    ? el("div", { class: "ni-risks" }, severityBadge(d.highest_risk), d.risks.length > 1 ? el("span", { class: "ni-count", text: `×${d.risks.length}` }) : null)
    : el("span", { class: "ni-none", text: t("noRisk") });
  const classes = [d.present ? "" : "ni-missing", d.id === selectedId ? "ni-selected" : ""].filter(Boolean).join(" ");
  return el(
    "tr",
    { class: classes || undefined, dataset: { id: d.id } },
    el("td", { class: "mono" }, d.ip),
    el("td", { class: "mono ni-wide" }, d.mac ?? "—"),
    el("td", { class: "ni-wide" }, vendorOf(d)),
    el("td", {}, el("div", { class: "ni-name" }, deviceButton(d.id, d.label), statusBadges(d)), el("div", { class: "ni-sub mono", text: `${d.mac ?? "—"} · ${vendorOf(d)}` }), el("div", { class: "ni-sub ni-sub-ports mono", text: `${t("colPorts")}: ${d.ports.map((p) => p.port).join(" ") || "—"}` })),
    el("td", { class: "ni-ports ni-portcol mono" }, d.ports.length ? d.ports.map((p) => el("span", { title: p.service || undefined, text: String(p.port) })) : "—"),
    el("td", {}, risk),
  );
}

function renderTable(devices, flash = new Set()) {
  const rows = devices.map((d) => {
    const row = rowFor(d);
    if (flash.has(d.id)) row.classList.add("d-flash");
    return row;
  });
  if (!rows.length) {
    rows.push(el("tr", {}, el("td", { colspan: 6, class: "ni-empty", text: t(listing?.scan ? "noMatch" : "noScan") })));
  }
  ui.tbody.replaceChildren(...rows);
  ui.count.textContent = listing?.summary ? t("showing", { shown: devices.length, total: listing.summary.total }) : "";
}

function applyListing(result, flash) {
  listing = result;
  renderScanInfo(result.scan);
  renderSummary(result.summary);
  renderTable(result.devices, flash);
}

function changeDetail(c) {
  switch (c.kind) {
    case "new":
      return c.ports.length ? t("chOpen", { ports: portList(c.ports) }) : t("chNoPorts");
    case "port_opened":
    case "port_closed":
      return portList(c.ports);
    case "gone":
      return t("chWas", { ip: c.old_ip });
    case "ip_changed":
      return `${c.old_ip} → ${c.new_ip}`;
    default:
      return c.ip;
  }
}

function changeItem(c) {
  return el(
    "li",
    { class: "d-enter" },
    el("span", { class: "ni-kind" }, t(`ch_${c.kind}`)),
    el(
      "div",
      { class: "ni-change" },
      el("div", { class: "ni-name" }, deviceButton(c.device_id, c.label), c.flagged ? el("span", { class: "d-badge fail", text: t("flagged") }) : null),
      el("div", { class: "mono ni-detail", text: changeDetail(c) }),
    ),
  );
}

function renderAlert(result) {
  if (!result?.scan) return ui.alert.replaceChildren();
  ui.alert.replaceChildren(
    el("hr", { class: "d-rule" }),
    el("span", { class: "d-label", text: t("alertTitle") }),
    result.alert ? el("pre", { class: "ni-pre d-enter", text: result.alert }) : el("p", { class: "d-note", text: t("noAlert") }),
    el("p", { class: "d-note", text: t("alertNote") }),
  );
}

/** The changes of the last scan; with `items` = false the list is left for the script to fill. */
function renderChanges(result, { items = true } = {}) {
  const scan = result?.scan;
  ui.changesTitle.textContent = t("changesTitle", { id: scan?.id ?? 2 });
  let body;
  if (!scan) body = el("p", { class: "d-note", text: t("changesWait") });
  else if (scan.first) body = el("p", { class: "d-note", text: t("firstScan") });
  else if (!result.changes.length) body = el("p", { class: "d-note", text: t("noChanges") });
  else body = el("ul", { class: "d-log ni-changes" }, items ? result.changes.map(changeItem) : []);
  ui.changes.replaceChildren(body);
  if (items) renderAlert(result);
  else ui.alert.replaceChildren();
  return body;
}

function fact(label, value, mono = false) {
  return el("div", {}, el("span", { class: "d-label", text: label }), el("div", { class: `ni-fact${mono ? " mono" : ""}`, text: value }));
}

function riskBlock(r) {
  return el(
    "div",
    { class: "ni-risk d-enter" },
    el("div", { class: "d-stack ni-risk-side" }, severityBadge(r.severity), el("span", { class: "mono d-note", text: t("portList", { ports: portList(r.ports) }) })),
    el(
      "div",
      {},
      el("h4", { text: ruleText(r.code, "title", r.title) }),
      el("p", { text: ruleText(r.code, "why", r.why) }),
      el("p", { class: "ni-fix" }, el("span", { class: "d-label", text: t("whatToDo") }), el("br"), ruleText(r.code, "fix", r.fix)),
    ),
  );
}

function simControls(d) {
  if (!d.mac) return null;
  const closed = new Set(d.sim.closed);
  const riskyPorts = [...new Map(d.risks.flatMap((r) => r.ports).map((p) => [p.port, p])).values()].filter((p) => !closed.has(p.port));
  const buttons = riskyPorts.map((p) =>
    el("button", { class: "d-btn", type: "button", disabled: !live, onclick: () => simulate(() => py.call("close_port", d.id, p.port)) }, t("closePort", { port: p.port, service: p.service })),
  );
  if (d.present || d.sim.unplugged) {
    buttons.push(
      el("button", { class: "d-btn", type: "button", disabled: !live, onclick: () => simulate(() => py.call("set_unplugged", d.id, !d.sim.unplugged)) }, t(d.sim.unplugged ? "plugBack" : "unplug")),
    );
  }
  const pending = [
    d.sim.closed.length ? el("p", { class: "d-note ni-pending", text: t("closedPending", { ports: d.sim.closed.join(", ") }) }) : null,
    d.sim.unplugged ? el("p", { class: "d-note ni-pending", text: t("unpluggedPending") }) : null,
  ];
  return el(
    "div",
    { class: "d-stack ni-sim" },
    el("div", { class: "d-row" }, el("span", { class: "d-label", text: t("simTitle") }), el("span", { class: "d-badge sim", text: t("simOffice") })),
    el("div", { class: "d-row" }, buttons),
    pending,
    el("p", { class: "d-note", text: t("simNote") }),
  );
}

function renderDetail(d, { risks = true } = {}) {
  lastDetail = d;
  if (!d) return ui.detail.replaceChildren(el("p", { class: "d-note", text: t("detailEmpty") }));
  const owner = [d.owner, d.location].filter(Boolean).join(" · ") || "—";
  const riskList = el("div", { class: "ni-risklist" }, risks ? d.risks.map(riskBlock) : []);
  if (risks && !d.risks.length) riskList.append(el("p", { class: "d-note", text: t("noRisks") }));
  ui.detail.replaceChildren(
    el("div", { class: "ni-name ni-title" }, el("h3", { class: "d-title", text: d.label }), statusBadges(d)),
    el(
      "div",
      { class: "ni-facts" },
      fact(t("fIp"), d.ip, true),
      fact(t("fMac"), d.mac ?? "—", true),
      fact(t("fVendor"), d.randomised ? t("randomisedLong") : d.vendor ?? t("unknownVendor")),
      fact(t("fHost"), d.hostname ?? "—", true),
      fact(t("fPorts"), d.ports.length ? portList(d.ports) : t("noPorts"), true),
      fact(t("fOwner"), owner),
      fact(t("fFirst"), when(d.first_seen)),
      fact(t("fLast"), when(d.last_seen)),
    ),
    el("div", { class: "ni-head" }, el("span", { class: "d-label", text: t("risksTitle") }), el("span", { class: "d-label", text: String(d.risks.length) })),
    riskList,
    simControls(d),
    el(
      "details",
      { class: "ni-more" },
      el("summary", { class: "d-label", text: `${t("ipHistory")} · ${t("history")}` }),
      el(
        "table",
        { class: "d-table" },
        el("tbody", {}, d.ip_records.map((r) => el("tr", {}, el("td", { class: "mono", text: r.ip }), el("td", { text: `${when(r.first_seen)} – ${when(r.last_seen)}` })))),
      ),
      el(
        "ul",
        { class: "d-log ni-changes" },
        d.history.map((c) => el("li", {}, el("span", { class: "ni-kind" }, t(`ch_${c.kind}`)), el("div", {}, el("div", { class: "mono ni-detail", text: changeDetail(c) }), el("div", { class: "d-note", text: t("scanN", { id: c.scan_id }) })))),
      ),
      el("p", { class: "d-note mono", text: `${t("fKey")}: ${d.key}` }),
    ),
  );
  return riskList;
}

function markSelected() {
  for (const row of ui.tbody.querySelectorAll("tr[data-id]")) row.classList.toggle("ni-selected", Number(row.dataset.id) === selectedId);
}

function showExport(result, kind, download) {
  if (blobUrl) URL.revokeObjectURL(blobUrl);
  const blob = new Blob([result.text], { type: kind === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8" });
  blobUrl = URL.createObjectURL(blob);
  const link = el("a", { class: "d-btn solid", href: blobUrl, download: result.filename, text: t("save", { file: result.filename }) });
  const preview = result.text.replace(/^﻿/, "").split(/\r?\n/).slice(0, kind === "csv" ? 5 : 16).join("\n");
  ui.exportOut.replaceChildren(
    el("p", { class: "d-note mono", text: t("exportInfo", { file: result.filename, rows: result.rows, size: size(blob.size) }) }),
    el("pre", { class: "ni-pre code d-enter", text: `${preview}\n…` }),
    el("div", {}, link),
  );
  if (download) link.click();
}

// --- Actions (all through Python) -------------------------------------------------------

function setBusy(on) {
  busy = on;
  ui.scanButton.disabled = on || !live;
  ui.scanButton.textContent = on ? t("scanning") : t("runScan", { n: (listing?.scan?.id ?? 0) + 1 });
}

async function refresh(flash) {
  try {
    applyListing(await py.call("devices", ...filterArgs()), flash);
  } catch (error) {
    showError(error);
  }
}

async function runScan() {
  if (busy) return;
  setBusy(true);
  ui.error.hidden = true;
  try {
    const result = await py.call("scan");
    lastScan = result;
    const flash = new Set(result.changes.map((c) => c.device_id));
    if (filtersActive()) await refresh(flash);
    else applyListing(result, flash);
    renderChanges(result);
    if (selectedId !== null) renderDetail(await py.call("device", selectedId));
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function openDevice(id) {
  if (!live) return;
  selectedId = id;
  markSelected();
  try {
    renderDetail(await py.call("device", id));
    demo.player.show(ui.detailPanel);
  } catch (error) {
    showError(error);
  }
}

async function simulate(action) {
  try {
    await action();
    renderDetail(await py.call("device", selectedId));
  } catch (error) {
    showError(error);
  }
}

async function exportFile(kind, download) {
  try {
    showExport(await py.call(kind === "csv" ? "export_csv" : "export_json"), kind, download);
  } catch (error) {
    showError(error);
  }
}

// --- Autoplay ---------------------------------------------------------------------------

demo.autoplay({
  async reset() {
    live = false;
    busy = false;
    listing = lastScan = lastDetail = null;
    selectedId = null;
    info = await py.call("start", TZ);
    build();
  },

  async script(play) {
    const call = async (...args) => {
      const result = await py.call(...args);
      play.check(); // a Replay during the call: stop before drawing into the new run
      return result;
    };
    await play.wait(900);

    // Scan 1: the register fills row by row.
    ui.scanButton.textContent = t("scanning");
    const first = await call("scan");
    lastScan = first;
    listing = first;
    renderScanInfo(first.scan);
    ui.tbody.replaceChildren();
    for (const [i, d] of first.devices.entries()) {
      const row = rowFor(d);
      row.classList.add("d-enter");
      ui.tbody.append(row);
      ui.count.textContent = t("showing", { shown: i + 1, total: first.summary.total });
      if (i === 8) play.show(ui.tableBox);
      await play.wait(170);
    }
    renderSummary(first.summary);
    renderChanges(first);
    await play.wait(2600);

    ui.note.textContent = t("adminNote");
    play.show(ui.note);
    await play.wait(2800);

    // Scan 2: the diff.
    ui.scanButton.textContent = t("scanning");
    await play.wait(700);
    const second = await call("scan");
    lastScan = second;
    applyListing(second, new Set(second.changes.map((c) => c.device_id)));
    await play.wait(1600);
    const list = renderChanges(second, { items: false });
    play.show(ui.changesPanel);
    for (const change of second.changes) {
      list.append(changeItem(change));
      await play.wait(850);
    }
    renderAlert(second);
    await play.wait(3200);

    // Search, then open the device whose risky port just opened.
    play.show(ui.search);
    await play.type(ui.search, "camera");
    applyListing(await call("devices", ...filterArgs()));
    await play.wait(1500);
    const target = second.changes.find((c) => c.kind === "port_opened") ?? second.changes.find((c) => c.flagged);
    if (target) {
      selectedId = target.device_id;
      markSelected();
      const detail = await call("device", target.device_id);
      const risks = renderDetail(detail, { risks: false });
      play.show(ui.detailPanel);
      await play.wait(900);
      for (const r of detail.risks) {
        risks.append(riskBlock(r));
        await play.wait(1300);
      }
      await play.wait(3200);
    }
    await play.type(ui.search, "");
    applyListing(await call("devices", ...filterArgs()));
    await play.wait(900);

    // Export: the CSV, ready to save.
    play.show(ui.exportPanel);
    showExport(await call("export_csv"), "csv", false);
    await play.wait(2400);
  },

  interactive() {
    live = true;
    for (const control of [ui.scanButton, ui.search, ui.risk, ui.status, ui.csvButton, ui.jsonButton]) control.disabled = false;
    ui.note.textContent = t("yourTurn");
    renderScanInfo(listing?.scan ?? null);
    renderTable(listing?.devices ?? []);
    renderChanges(lastScan);
    renderDetail(lastDetail);
  },
});
