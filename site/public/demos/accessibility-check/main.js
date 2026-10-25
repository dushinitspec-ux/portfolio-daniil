// Accessibility Check demo: the project's real WCAG rules (BeautifulSoup + lxml), report
// aggregation and contrast maths, run in the browser on the bundled Sample Shop pages, on HTML
// the visitor pastes (parsed by Python as text, never inserted here), and on two colours.
// Everything shown comes from py.call(...) into app/web_demo.py.
import { createDemo, el, lang } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: (strings[lang] ?? strings.en).title, strings });
const { t } = demo;
const py = await demo.python();

const BADGE = { fail: "fail", warning: "warn", pass: "ok", "n/a": "sim" };
const STATUS = { fail: "fail", warning: "warning", pass: "pass", "n/a": "na" };
const SEVERITY_BADGE = { high: "fail", medium: "warn", low: "sim" };
const HEX = /^#[0-9a-f]{6}$/i;

let ui = {};
let locked = true;
let busy = false;

function setCaption(key) {
  ui.caption.textContent = t(key);
  ui.caption.classList.remove("d-enter");
  void ui.caption.offsetWidth;
  ui.caption.classList.add("d-enter");
}

function setLocked(value) {
  locked = value;
  for (const input of [ui.fg, ui.bg, ui.size, ui.paste]) input.readOnly = value;
  for (const control of [ui.scanBroken, ui.scanFixed, ui.fgPick, ui.bgPick, ui.bold, ui.checkButton, ui.pasteButton]) {
    control.disabled = value || busy;
  }
}

async function call(name, ...args) {
  busy = true;
  setLocked(locked);
  try {
    const started = performance.now();
    const result = await py.call(name, ...args);
    ui.ms = t("ranIn", { ms: Math.max(1, Math.round(performance.now() - started)) });
    return result;
  } finally {
    busy = false;
    setLocked(locked);
  }
}

// --- the report --------------------------------------------------------------------------

const statusBadge = (status) => el("span", { class: `d-badge ${BADGE[status]}`, text: t(STATUS[status]) });

function stat(labelKey, value, tone) {
  return el("div", { class: "ac-stat", dataset: { tone: value ? tone : "zero" } }, el("b", { text: value }), el("span", { text: t(labelKey) }));
}

function renderSummary(result, name) {
  const s = result.summary;
  const severity = s.issues_by_severity;
  ui.summary.replaceChildren(
    el("div", { class: "ac-head" }, el("span", { class: "d-label", text: t("reportOf", { name }) }), el("span", { class: "d-note mono", text: ui.ms })),
    el(
      "div",
      { class: "ac-stats" },
      stat("checksFail", s.checks.fail, "fail"),
      stat("checksWarn", s.checks.warning, "warn"),
      stat("checksPass", s.checks.pass, "ok"),
      stat("checksNa", s.checks["n/a"], "na"),
    ),
    el(
      "p",
      { class: "d-row ac-severity" },
      el("span", { class: "d-note", text: `${t("findings")}:` }),
      ...["high", "medium", "low"].map((key) => el("span", { class: `d-badge ${severity[key] ? SEVERITY_BADGE[key] : "sim"}`, text: `${t(key)} ${severity[key]}` })),
    ),
  );
}

function renderPages(result, hidden) {
  const items = [];
  for (const page of result.pages) {
    let text;
    if (page.analysed) text = page.issue_count ? t("pAnalysed", { n: page.issue_count }) : t("pClean");
    else if (page.duplicate_of) text = t("pDuplicate", { url: page.duplicate_of });
    else text = t("pNotFound", { status: page.status ?? "—" });
    const tone = page.analysed ? (page.issue_count ? "fail" : "ok") : "muted";
    items.push(
      el(
        "li",
        { class: "d-enter", hidden, dataset: { tone } },
        el("span", { class: "mono ac-code", text: page.status ?? "—" }),
        el("span", { class: "mono ac-path", text: page.path }),
        el("span", { class: "ac-what", text }),
      ),
    );
  }
  for (const skip of result.skipped) {
    const text = skip.reason === "blocked by robots.txt" ? t("pRobots") : skip.reason.startsWith("page limit") ? t("pLimit") : skip.reason;
    items.push(el("li", { class: "d-enter", hidden, dataset: { tone: "muted" } }, el("span", { class: "mono ac-code", text: "—" }), el("span", { class: "mono ac-path", text: skip.path }), el("span", { class: "ac-what", text })));
  }
  const s = result.summary;
  ui.pages.replaceChildren(
    el("span", { class: "d-label", text: t("pagesTitle") }),
    el("p", { class: "d-note", text: t("pagesNote", { analysed: s.pages_analysed, total: s.pages_requested }) }),
    el("ul", { class: "ac-pages" }, items),
  );
  return items;
}

function renderCriteria(result) {
  const rows = result.summary.criteria.map((c) =>
    el(
      "tr",
      { dataset: { status: c.status } },
      el("td", { class: "mono" }, el("a", { href: c.url, target: "_blank", rel: "noopener", text: c.number })),
      el("td", { text: c.name }),
      el("td", { class: "mono", text: c.obsolete ? t("removed") : c.level }),
      el("td", {}, statusBadge(c.status)),
      el("td", { class: "num", text: c.issues || "" }),
    ),
  );
  ui.criteria.replaceChildren(
    el("span", { class: "d-label", text: t("criteriaTitle") }),
    el(
      "div",
      { class: "d-scroll" },
      el(
        "table",
        { class: "d-table ac-criteria" },
        el("thead", {}, el("tr", {}, el("th", { text: "WCAG" }), el("th", { text: t("colCriterion") }), el("th", { text: t("colLevel") }), el("th", { text: t("colStatus") }), el("th", { class: "num", text: t("colIssues") }))),
        el("tbody", {}, rows),
      ),
    ),
  );
}

function swatches(colors) {
  return el(
    "span",
    { class: "ac-swatches" },
    colors.map((color) => el("span", { class: "ac-swatch", title: color, style: { background: HEX.test(color) ? color : "transparent" } })),
  );
}

function ruleCard(rule, result, levels, hidden) {
  const info = result.rules_info[rule.rule_id];
  const criteria = rule.criteria.map((n) => `${n} ${levels[n] ?? ""}`.trim()).join(" · ");
  const count = rule.pages_affected === 1 ? t("issuesOn1", { n: rule.issues }) : t("issuesOn", { n: rule.issues, pages: rule.pages_affected });
  const groups = result.pages
    .filter((page) => page.issues.some((i) => i.rule_id === rule.rule_id))
    .map((page) =>
      el(
        "div",
        { class: "ac-page-findings" },
        el("p", { class: "mono ac-path", text: page.path }),
        el(
          "ul",
          {},
          page.issues
            .filter((i) => i.rule_id === rule.rule_id)
            .map((issue) =>
              el(
                "li",
                {},
                el("p", { class: "ac-msg" }, el("span", { class: `d-badge ${SEVERITY_BADGE[issue.severity]}`, text: t(issue.severity) }), " ", issue.colors ? swatches(issue.colors) : null, issue.message),
                issue.snippet ? el("code", { class: "ac-snippet", text: issue.snippet }) : null,
              ),
            ),
        ),
      ),
    );
  return el(
    "details",
    { class: "ac-rule d-enter", hidden, dataset: { status: rule.status, rule: rule.rule_id } },
    el(
      "summary",
      {},
      statusBadge(rule.status),
      el("span", { class: "ac-rule-title", text: rule.title }),
      el("span", { class: "ac-rule-meta mono", text: `${criteria} · ${count}` }),
    ),
    el(
      "div",
      { class: "ac-rule-body" },
      el("p", {}, el("b", { text: `${t("fix")}: ` }), info.fix),
      el("p", { class: "d-note" }, el("b", { text: `${t("why")}: ` }), info.why),
      info.advisory ? el("p", { class: "d-note mono ac-advisory", text: t("advisory") }) : null,
      groups,
    ),
  );
}

function renderRules(result, hidden) {
  const levels = Object.fromEntries(result.summary.criteria.map((c) => [c.number, c.obsolete ? "" : c.level]));
  const open = result.summary.rules.filter((r) => r.status === "fail" || r.status === "warning");
  const cards = open.map((rule) => ruleCard(rule, result, levels, hidden));
  const chipList = (status, labelKey) => {
    const rules = result.summary.rules.filter((r) => r.status === status);
    if (!rules.length) return null;
    return el(
      "div",
      { class: "ac-chips" },
      el("span", { class: "d-label", text: `${t(labelKey)} · ${rules.length}` }),
      el("div", { class: "d-row" }, rules.map((r) => el("span", { class: `ac-chip ${status === "pass" ? "ok" : ""}`, text: r.title }))),
    );
  };
  ui.rules.replaceChildren(
    ...[
      el("span", { class: "d-label", text: t("rulesTitle") }),
      cards.length ? el("div", { class: "ac-rules" }, cards) : null,
      chipList("pass", "passedRules"),
      chipList("n/a", "naRules"),
      el("p", { class: "d-note", text: t("ruleLang") }),
    ].filter(Boolean),
  );
  return cards;
}

function renderReport(result, name, { hidden = false } = {}) {
  renderSummary(result, name);
  const pages = renderPages(result, hidden);
  renderCriteria(result);
  const cards = renderRules(result, hidden);
  return { pages, cards };
}

async function scan(sample, options) {
  const result = await call("scan_sample", sample);
  return renderReport(result, t(sample), options);
}

// --- contrast checker ----------------------------------------------------------------------

async function checkContrast() {
  const result = await call("contrast", ui.fg.value, ui.bg.value, Number(ui.size.value) || 16, ui.bold.checked);
  if (result.error) {
    const key = { foreground: "errForeground", background: "errBackground", "background-alpha": "errAlpha" }[result.error];
    ui.contrastOut.replaceChildren(el("p", { class: "ac-error", role: "alert", text: t(key) }));
    return result;
  }
  if (HEX.test(result.background)) ui.bgPick.value = result.background;
  if (HEX.test(ui.fg.value)) ui.fgPick.value = ui.fg.value.toLowerCase();
  else if (!result.blended && HEX.test(result.foreground)) ui.fgPick.value = result.foreground;
  const size = result.large ? "large" : "normal";
  const cell = (level, text) => {
    const check = result.checks.find((c) => c.level === level && c.text === text);
    return el(
      "td",
      { class: text === size ? "ac-yours" : "" },
      el("span", { class: `d-badge ${check.pass ? "ok" : "fail"}`, text: check.pass ? t("pass") : t("fail") }),
      el("span", { class: "d-note mono", text: ` ${check.need}:1` }),
    );
  };
  ui.contrastOut.replaceChildren(
    ...[
      el(
        "div",
        { class: "ac-preview", style: { color: result.foreground, background: result.background, fontSize: `${Math.min(Math.max(Number(ui.size.value) || 16, 8), 40)}px`, fontWeight: ui.bold.checked ? "700" : "400" } },
        t("sampleText"),
      ),
      el("p", { class: "d-big ac-ratio d-enter", text: result.shown }),
      el("p", { class: "d-note", text: t(result.large ? "largeYes" : "largeNo") }),
      result.blended ? el("p", { class: "d-note", text: t("blended") }) : null,
      el(
        "table",
        { class: "d-table ac-levels" },
        el(
          "thead",
          {},
          el("tr", {}, el("th", { text: "WCAG" }), ...["normal", "large"].map((text) => el("th", { class: text === size ? "ac-yours" : "" }, t(`${text}Text`), text === size ? el("span", { class: "ac-you", text: ` · ${t("yourText")}` }) : null))),
        ),
        el("tbody", {}, el("tr", {}, el("th", { text: "AA · 1.4.3" }), cell("AA", "normal"), cell("AA", "large")), el("tr", {}, el("th", { text: "AAA · 1.4.6" }), cell("AAA", "normal"), cell("AAA", "large"))),
      ),
      el("p", { class: "d-note", text: t("aaaNote") }),
    ].filter(Boolean),
  );
  return result;
}

function colorField(labelKey, pickKey, id, value) {
  const text = el("input", { class: "d-input mono", id, value, autocomplete: "off", spellcheck: "false" });
  const pick = el("input", { class: "ac-pick", type: "color", value, "aria-label": t(pickKey) });
  pick.addEventListener("input", () => {
    text.value = pick.value;
  });
  text.addEventListener("input", () => {
    if (HEX.test(text.value.trim())) pick.value = text.value.trim().toLowerCase();
  });
  return { text, pick, node: el("div", { class: "d-field" }, el("label", { class: "d-label", for: id, text: t(labelKey) }), el("div", { class: "ac-color" }, pick, text)) };
}

// --- page layout, autoplay and the visitor's turn -------------------------------------------

function build() {
  ui = { ms: "" };
  ui.caption = el("p", { class: "ac-caption", "aria-live": "polite" });
  ui.scanBroken = el("button", { class: "d-btn solid", type: "button", text: t("scanBroken"), disabled: true });
  ui.scanFixed = el("button", { class: "d-btn", type: "button", text: t("scanFixed"), disabled: true });
  ui.scanBroken.addEventListener("click", () => !locked && scan("broken"));
  ui.scanFixed.addEventListener("click", () => !locked && scan("fixed"));
  ui.summary = el("div", { class: "d-panel ac-summary" });
  ui.pages = el("div", { class: "d-panel" });
  ui.criteria = el("div", { class: "d-panel" });
  ui.rules = el("div", { class: "d-panel" });

  const fg = colorField("textColor", "pickText", "ac-fg", "#000000");
  const bg = colorField("bgColor", "pickBg", "ac-bg", "#ffffff");
  ui.fg = fg.text;
  ui.fgPick = fg.pick;
  ui.bg = bg.text;
  ui.bgPick = bg.pick;
  ui.size = el("input", { class: "d-input", id: "ac-size", type: "number", min: "6", max: "96", step: "0.5", value: "16", inputmode: "decimal" });
  ui.bold = el("input", { type: "checkbox", id: "ac-bold" });
  ui.checkButton = el("button", { class: "d-btn solid", type: "submit", text: t("check"), disabled: true });
  ui.contrastOut = el("div", { class: "ac-contrast-out", "aria-live": "polite" });
  const contrastForm = el(
    "form",
    { class: "d-stack", novalidate: true },
    el("div", { class: "ac-two" }, fg.node, bg.node),
    el(
      "div",
      { class: "ac-two" },
      el("div", { class: "d-field" }, el("label", { class: "d-label", for: "ac-size", text: t("fontSize") }), ui.size),
      el("label", { class: "ac-check", for: "ac-bold" }, ui.bold, el("span", { text: t("bold") })),
    ),
    el("div", {}, ui.checkButton),
  );
  contrastForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!locked) checkContrast();
  });

  ui.paste = el("textarea", { class: "d-textarea mono ac-paste", id: "ac-paste", rows: "12", spellcheck: "false" });
  ui.paste.value = t("pasteSample");
  ui.pasteButton = el("button", { class: "d-btn solid", type: "submit", text: t("pasteRun"), disabled: true });
  ui.pasteError = el("p", { class: "ac-error", role: "alert", hidden: true });
  const pasteForm = el(
    "form",
    { class: "d-stack", novalidate: true },
    el("label", { class: "d-label", for: "ac-paste", text: t("pasteLabel") }),
    ui.paste,
    el("div", { class: "d-row" }, ui.pasteButton),
    ui.pasteError,
    el("p", { class: "d-note", text: t("pasteNote") }),
  );
  pasteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (locked) return;
    ui.pasteError.hidden = true;
    if (!ui.paste.value.trim()) {
      ui.pasteError.textContent = t("pasteEmpty");
      ui.pasteError.hidden = false;
      return;
    }
    try {
      const result = await call("check_html", ui.paste.value);
      renderReport(result, t("pasted", { kb: new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(result.bytes / 1024) }));
    } catch (error) {
      ui.pasteError.textContent = String(error.message).split("\n").filter(Boolean).pop();
      ui.pasteError.hidden = false;
    }
  });

  demo.stage.replaceChildren(
    ui.caption,
    el(
      "div",
      { class: "d-panel d-stack" },
      el("div", { class: "d-row" }, ui.scanBroken, ui.scanFixed, el("span", { class: "d-badge sim", text: t("bundled") })),
      el("p", { class: "d-note", text: t("noCrawl") }),
    ),
    ui.summary,
    el("div", { class: "d-cols" }, ui.pages, ui.criteria),
    el(
      "div",
      { class: "d-cols wide-left" },
      ui.rules,
      el(
        "div",
        { class: "d-stack ac-side" },
        el("div", { class: "d-panel", id: "ac-contrast" }, el("span", { class: "d-label", text: t("contrastTitle") }), contrastForm, ui.contrastOut),
        el("div", { class: "d-panel" }, el("span", { class: "d-label", text: t("pasteTitle") }), pasteForm),
      ),
    ),
  );
  setLocked(true);
}

const cardFor = (cards, rule) => cards.find((card) => card.dataset.rule === rule);

demo.autoplay({
  reset() {
    build();
  },
  async script(play) {
    setCaption("a1");
    await play.wait(1800);
    const broken = await scan("broken", { hidden: true });
    for (const item of broken.pages) {
      item.hidden = false;
      await play.wait(450);
    }
    await play.wait(600);
    setCaption("a2");
    for (const card of broken.cards) {
      card.hidden = false;
      await play.wait(480);
    }
    await play.wait(1200);

    setCaption("a3");
    const images = cardFor(broken.cards, "image-alt");
    images.open = true;
    await play.wait(5000);
    images.open = false;

    setCaption("a4");
    const contrast = cardFor(broken.cards, "color-contrast");
    contrast.open = true;
    await play.wait(1800);
    await play.type(ui.fg, "#777777");
    ui.fgPick.value = "#777777";
    await play.type(ui.bg, "#ffffff");
    await play.wait(400);
    await checkContrast();
    await play.wait(3200);
    await play.type(ui.fg, "#767676");
    ui.fgPick.value = "#767676";
    await play.wait(400);
    await checkContrast();
    await play.wait(3200);
    contrast.open = false;

    setCaption("a5");
    await scan("fixed");
    await play.wait(3500);
  },
  interactive() {
    setCaption("ready");
    setLocked(false);
  },
});
