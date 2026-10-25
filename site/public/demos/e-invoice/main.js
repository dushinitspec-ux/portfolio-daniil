// E-Invoice demo: a bundled sample PDF -> extracted fields -> EN 16931 / XRechnung rules ->
// XRechnung UBL XML. Every value on screen comes from py.call("convert", ...), which runs the
// project's own extractor, derivation, validator and XML writer (app/web_demo.py).
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: (strings[lang] ?? strings.en).title, strings });
const { t } = demo;
const py = await demo.python();

const START_SAMPLE = "de-muster-gmbh-with-errors";
const NET_FIX = "882.30";
const IBAN_FIX = "DE52000000000012345678";

const GROUPS = [
  ["gInvoice", ["number", "issue_date", "due_date", "buyer_reference"]],
  ["gSeller", ["seller.name", "seller.vat_id", "seller.electronic_address"], "seller_address"],
  ["gBuyer", ["buyer.name", "buyer.vat_id", "buyer.electronic_address"], "buyer_address"],
  ["gPayment", ["payment.iban"]],
  ["gLines", null],
  ["gTotals", ["totals.line_net_total", "totals.tax_exclusive", "totals.vat_total", "totals.tax_inclusive", "totals.payable"]],
];
const DATES = new Set(["issue_date", "due_date"]);
const LINE_COLUMNS = [
  ["quantity", "colQty"],
  ["net_price", "colPrice"],
  ["net_amount", "colAmount"],
];
const ERRORS = { email: "errEmail", date: "errDate", number: "errNumber", unknown: "errUnknown" };

const samples = await py.call("samples");

let locked = true;
let current = START_SAMPLE;
let baseline = {};
let inputs = new Map();
let previous = new Map();
let busy = false;
let ui = {};

const fieldId = (path) => `f-${path.replace(/\./g, "-")}`;
const fieldLabel = (path) => t(path.split(".").pop());
const sampleLabel = (s) => {
  const key = `s_${s.id.replace(/-/g, "_")}`;
  const text = t(key);
  return text === key ? s.file : text;
};

function setCaption(key) {
  ui.caption.textContent = t(key);
  ui.caption.classList.remove("d-enter");
  void ui.caption.offsetWidth;
  ui.caption.classList.add("d-enter");
}

function setLocked(value) {
  locked = value;
  for (const input of inputs.values()) input.readOnly = value;
  for (const control of [ui.select, ui.convert, ui.validate, ui.download]) if (control) control.disabled = value || busy;
}

// --- the source: picture of page 1 and what was pre-extracted ---------------------------

function renderSource() {
  const sample = samples.find((s) => s.id === current);
  ui.select.value = current;
  const src = `pages/${current}.png`;
  ui.source.replaceChildren(
    el(
      "a",
      { class: "ei-thumb", href: src, target: "_blank", rel: "noopener", title: t("openPreview") },
      el("img", { src, width: 560, height: 792, alt: t("preview", { file: sample.file }) }),
    ),
    el(
      "div",
      { class: "d-stack" },
      el("p", { class: "mono ei-file", text: sample.file }),
      el("p", { class: "d-note", text: t("pdfMeta", { pages: sample.pages, words: sample.words }) }),
      el("div", { class: "d-row" }, el("span", { class: "d-badge sim", text: t("preBadge") }), el("span", { class: "d-badge sim", text: t("sample") })),
      el("p", { class: "d-note", text: t("preNote") }),
    ),
  );
}

// --- the editable fields -------------------------------------------------------------------

function field(path, result) {
  const isDate = DATES.has(path);
  const input = el("input", {
    class: "d-input",
    id: fieldId(path),
    name: path,
    type: isDate ? "date" : path.endsWith("electronic_address") ? "email" : "text",
    inputmode: path.startsWith("totals.") ? "decimal" : undefined,
    autocomplete: "off",
    spellcheck: "false",
    dataset: { term: result.terms[path] },
  });
  inputs.set(path, input);
  return el(
    "div",
    { class: "ei-field", dataset: { term: result.terms[path] } },
    el(
      "label",
      { for: input.id },
      el("span", { text: fieldLabel(path) }),
      el("span", { class: "ei-term", text: result.terms[path] }),
      el("span", { class: "ei-flags" }),
    ),
    input,
  );
}

function linesTable(result) {
  const head = el(
    "tr",
    {},
    el("th", { text: t("colPos") }),
    el("th", { text: t("colName") }),
    el("th", { class: "num", text: t("colQty") }),
    el("th", { text: t("colUnit") }),
    el("th", { class: "num", text: t("colPrice") }),
    el("th", { class: "num", text: t("colVat") }),
    el("th", { class: "num", text: t("colAmount") }),
  );
  const rows = result.lines.map((line, index) => {
    const cell = (name, labelKey) => {
      const path = `lines.${index}.${name}`;
      const input = el("input", {
        class: "d-input ei-num",
        id: fieldId(path),
        name: path,
        inputmode: "decimal",
        autocomplete: "off",
        "aria-label": t("lineField", { field: t(labelKey), n: line.id }),
        dataset: { term: result.terms[path] },
      });
      inputs.set(path, input);
      return el("td", { class: "num", dataset: { term: result.terms[path] } }, input);
    };
    const vat = line.vat_rate === "" ? "—" : `${line.vat_rate} % ${line.vat_category}`;
    return el(
      "tr",
      {},
      el("td", { text: line.id }),
      el("td", { class: "ei-desc", text: line.name }),
      cell("quantity", "colQty"),
      el("td", { class: "mono", text: line.unit }),
      cell("net_price", "colPrice"),
      el("td", { class: "num mono ei-vat", text: vat }),
      cell("net_amount", "colAmount"),
    );
  });
  return el("div", { class: "d-scroll" }, el("table", { class: "d-table ei-lines" }, el("thead", {}, head), el("tbody", {}, rows)));
}

function buildForm(result) {
  inputs = new Map();
  const groups = GROUPS.map(([key, paths, address]) =>
    el(
      "fieldset",
      {},
      el("legend", { class: "d-label", text: t(key) }),
      paths ? el("div", { class: "ei-grid" }, paths.map((path) => field(path, result))) : linesTable(result),
      address && result[address] ? el("p", { class: "d-note ei-address", text: result[address] }) : null,
    ),
  );
  ui.errors = el("ul", { class: "ei-errors", hidden: true });
  ui.validate = el("button", { class: "d-btn solid", type: "submit", text: t("validate") });
  ui.timing = el("span", { class: "d-note mono" });
  ui.notes = el("ul", { class: "ei-notes" });
  const form = el(
    "form",
    { class: "ei-form", novalidate: true },
    groups,
    ui.errors,
    el("div", { class: "d-row ei-submit" }, ui.validate, ui.timing),
    el("div", { class: "ei-notes-box" }, el("p", { class: "d-label", text: t("notes") }), ui.notes),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!locked) revalidate();
  });
  ui.fields.replaceChildren(el("span", { class: "d-label", text: t("fieldsTitle") }), form);
}

function updateForm(result) {
  for (const [path, input] of inputs) {
    if (!(path in result.errors)) input.value = result.fields[path] ?? "";
    input.removeAttribute("aria-invalid");
    const box = input.closest(".ei-field, td");
    box.classList.remove("is-bad", "is-warn");
    box.classList.toggle("is-edited", result.edited.includes(path));
    box.querySelector(".ei-flags")?.replaceChildren();
  }
  // Fields named in a failed rule (its text or explanation mentions their BT number).
  for (const rule of result.rules) {
    if (rule.status !== "failed") continue;
    for (const term of rule.terms) {
      for (const input of inputs.values()) {
        if (input.dataset.term !== term) continue;
        const box = input.closest(".ei-field, td");
        box.classList.add(rule.severity === "fatal" ? "is-bad" : "is-warn");
        box.querySelector(".ei-flags")?.append(el("span", { class: `ei-flag ${rule.severity === "fatal" ? "" : "warn"}`, text: rule.id }));
      }
    }
  }
  const errors = Object.entries(result.errors);
  ui.errors.hidden = errors.length === 0;
  ui.errors.replaceChildren(
    ...errors.map(([path, code]) => {
      inputs.get(path)?.setAttribute("aria-invalid", "true");
      const name = path.startsWith("lines.") ? path : `${fieldLabel(path)} (${result.terms[path] ?? path})`;
      return el("li", { text: `${name}: ${t(ERRORS[code] ?? "errUnknown")}` });
    }),
  );
  ui.notes.replaceChildren(...[...result.warnings, ...result.derived].map((note) => el("li", { text: note })));
}

// --- the rules -------------------------------------------------------------------------------

function stat(labelKey, value, tone) {
  return el("div", { class: "ei-stat", dataset: { tone: value ? tone : "zero" } }, el("b", { text: value }), el("span", { text: t(labelKey) }));
}

function renderRules(result, { hideFailures = false } = {}) {
  const s = result.summary;
  const verdict = s.errors ? ["fail", "invalid"] : s.warnings ? ["warn", "validWarn"] : ["ok", "valid"];
  const failed = result.rules.filter((r) => r.status === "failed");
  const cards = failed.map((rule) =>
    el(
      "article",
      { class: `ei-rule ${rule.severity === "fatal" ? "is-fatal" : "is-warning"} d-enter`, hidden: hideFailures },
      el(
        "div",
        { class: "d-row" },
        el("span", { class: `d-badge ${rule.severity === "fatal" ? "fail" : "warn"}`, text: rule.id }),
        el("span", { class: "d-note", text: `${rule.source} · ${t(rule.severity === "fatal" ? "fatal" : "warning")}` }),
      ),
      el("p", { class: "ei-msg", text: rule.message }),
      el("p", { class: "ei-official" }, el("span", { class: "ei-term", text: `${t("officialText")}: ` }), rule.title),
    ),
  );
  const chips = result.rules.map((rule) => {
    const status = rule.status === "failed" ? (rule.severity === "fatal" ? "failed" : "warning") : rule.status === "passed" ? "passed" : "na";
    const changed = previous.has(rule.id) && previous.get(rule.id) !== status;
    return el("span", { class: `ei-chip${changed ? " d-flash" : ""}`, dataset: { status }, title: rule.title, text: rule.id });
  });
  previous = new Map(result.rules.map((r) => [r.id, r.status === "failed" ? (r.severity === "fatal" ? "failed" : "warning") : r.status === "passed" ? "passed" : "na"]));
  const statusText = { passed: t("stPassed"), failed: t("stFailed"), "n/a": t("stNa") };
  const table = el(
    "details",
    { class: "ei-all" },
    el("summary", { text: t("allRules", { n: s.total }) }),
    el(
      "div",
      { class: "d-scroll" },
      el(
        "table",
        { class: "d-table" },
        el(
          "tbody",
          {},
          result.rules.map((rule) =>
            el(
              "tr",
              {},
              el("td", { class: "mono", text: rule.id }),
              el("td", {}, el("span", { class: `d-badge ${rule.status === "passed" ? "ok" : rule.status === "failed" ? (rule.severity === "fatal" ? "fail" : "warn") : "sim"}`, text: statusText[rule.status] })),
              el("td", { class: "ei-rule-text" }, rule.title, rule.message ? el("span", { class: "d-note", text: ` — ${rule.message}` }) : null),
            ),
          ),
        ),
      ),
    ),
  );
  ui.rules.replaceChildren(
    el("div", { class: "ei-panel-head" }, el("span", { class: "d-label", text: t("rulesTitle") }), el("span", { class: "d-note mono", text: ui.lastMs })),
    el("div", { class: "ei-stats" }, stat("errors", s.errors, "fail"), stat("warnings", s.warnings, "warn"), stat("passed", s.passed, "ok"), stat("na", s.not_applicable, "na")),
    el("p", { class: "ei-verdict", dataset: { tone: verdict[0] }, text: t(verdict[1]) }),
    el("div", { class: "ei-fails", hidden: cards.length === 0 }, cards),
    el("div", { class: "ei-chips", "aria-hidden": "true" }, chips),
    table,
    el("p", { class: "d-note", text: t("ruleNote") }),
  );
  return cards;
}

// --- the XML ---------------------------------------------------------------------------------

function highlight(xml) {
  const pre = el("pre", { class: "ei-xml", tabindex: "0" });
  for (const part of xml.split(/(<[^>]+>)/)) {
    if (!part) continue;
    pre.append(part.startsWith("<") ? el("span", { class: "x-tag", text: part }) : el("span", { class: part.trim() ? "x-text" : "", text: part }));
  }
  return pre;
}

function xmlBadge(s) {
  if (s.errors) return el("span", { class: "d-badge fail", text: `${t("errors")}: ${s.errors}` });
  if (s.warnings) return el("span", { class: "d-badge warn", text: `${t("warnings")}: ${s.warnings}` });
  return el("span", { class: "d-badge ok", text: "XRechnung 3.0 ✓" });
}

function renderXml(result, { open = false } = {}) {
  const lines = result.xml.trimEnd().split("\n").length;
  const kb = (new Blob([result.xml]).size / 1024).toFixed(1);
  ui.download = el("button", { class: "d-btn solid", type: "button", text: t("download"), disabled: locked });
  ui.download.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([result.xml], { type: "application/xml" }));
    const link = el("a", { href: url, download: result.xml_name });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  ui.xmlDetails = el("details", { open, class: "ei-xml-box" }, el("summary", { text: t("showXml", { n: lines }) }), highlight(result.xml));
  ui.xml.replaceChildren(
    el("div", { class: "ei-panel-head" }, el("span", { class: "d-label", text: t("xmlTitle") }), el("span", { class: "d-note mono", text: `${result.xml_name} · ${kb} KB` })),
    el("div", { class: "d-row" }, ui.download, xmlBadge(result.summary)),
    ui.xmlDetails,
  );
}

// --- running Python -----------------------------------------------------------------------

async function run(edits) {
  busy = true;
  setLocked(locked);
  try {
    const started = performance.now();
    const result = await py.call("convert", current, edits);
    ui.lastMs = t("ranIn", { ms: Math.max(1, Math.round(performance.now() - started)) });
    return result;
  } finally {
    busy = false;
    setLocked(locked);
  }
}

function render(result, options = {}) {
  updateForm(result);
  ui.timing.textContent = ui.lastMs;
  const cards = renderRules(result, options);
  renderXml(result, options);
  return cards;
}

async function loadSample(id, options = {}) {
  current = id;
  previous = new Map();
  renderSource();
  const result = await run({});
  baseline = result.fields;
  buildForm(result);
  setLocked(locked);
  return render(result, options);
}

function collectEdits() {
  const edits = {};
  for (const [path, input] of inputs) if (input.value !== (baseline[path] ?? "")) edits[path] = input.value;
  return edits;
}

async function revalidate(options = {}) {
  const result = await run(collectEdits());
  return render(result, options);
}

// --- autoplay, then the visitor's turn -------------------------------------------------------

demo.autoplay({
  reset() {
    inputs = new Map();
    previous = new Map();
    current = START_SAMPLE;
    ui = { lastMs: "" };
    ui.caption = el("p", { class: "ei-caption", "aria-live": "polite" });
    ui.select = el("select", { class: "d-select", id: "ei-sample", disabled: true }, samples.map((s) => el("option", { value: s.id, text: sampleLabel(s) })));
    ui.convert = el("button", { class: "d-btn", type: "button", text: t("convert"), disabled: true });
    ui.select.addEventListener("change", () => !locked && loadSample(ui.select.value));
    ui.convert.addEventListener("click", () => !locked && loadSample(ui.select.value));
    ui.source = el("div", { class: "ei-source" });
    ui.fields = el("div", { class: "d-panel" });
    ui.rules = el("div", { class: "d-panel" });
    ui.xml = el("div", { class: "d-panel" });
    demo.stage.replaceChildren(
      ui.caption,
      el(
        "div",
        { class: "d-panel ei-head" },
        el("div", { class: "ei-pick" }, el("div", { class: "d-field" }, el("label", { class: "d-label", for: "ei-sample", text: t("sample") }), ui.select), ui.convert),
        ui.source,
      ),
      el("div", { class: "d-cols wide-left" }, ui.fields, el("div", { class: "d-stack ei-side" }, ui.rules, ui.xml)),
    );
    renderSource();
    locked = true;
  },
  async script(play) {
    setCaption("c1");
    await play.wait(2200);
    const cards = await loadSample(START_SAMPLE, { hideFailures: true });
    await play.wait(1800);
    setCaption("c2");
    for (const card of cards) {
      card.hidden = false;
      await play.wait(1700);
    }
    await play.wait(800);

    setCaption("c3");
    await play.wait(1500);
    await play.type(inputs.get("totals.line_net_total"), NET_FIX, { cps: 10 });
    await play.wait(300);
    await play.type(inputs.get("totals.tax_exclusive"), NET_FIX, { cps: 10 });
    await play.wait(700);
    ui.validate.classList.add("d-flash");
    await revalidate();
    await play.wait(3000);

    setCaption("c4");
    await play.wait(1800);
    await play.type(inputs.get("payment.iban"), IBAN_FIX, { cps: 16 });
    await play.wait(700);
    await revalidate();
    await play.wait(2500);

    setCaption("c5");
    ui.xmlDetails.open = true;
    await play.wait(3500);
  },
  interactive() {
    setCaption("cReady");
    setLocked(false);
  },
});
