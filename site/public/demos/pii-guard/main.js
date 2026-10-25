// PII Guard in the browser: the project's real detectors, policy, masking, gateway, offline
// demo model and audit log run in Pyodide (app/web_demo.py). Everything shown under the
// message comes from py.call(); this file only lays it out.
import { createDemo, el } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: "PII Guard demo", strings });
const { t, lang } = demo;
const py = await demo.python();
const setup = await py.call("setup");

const BRANDS = {
  visa: "Visa",
  mastercard: "Mastercard",
  amex: "American Express",
  mir: "Mir",
  jcb: "JCB",
  diners: "Diners Club",
  discover: "Discover",
  unionpay: "UnionPay",
  maestro: "Maestro",
};
const DECISION_BADGE = { masked: "ok", passed: "sim", blocked: "fail", error: "fail" };
const FAILED = ["empty", "too_long", "bad_policy", "error"];

const policy = {};
let ui = {};
let busy = false;

const typeLabel = (type) => t(`t_${type}`);

function lineLabel(line) {
  const key = `line_${line}`;
  const text = t(key);
  return text === key ? t("line_other") : text;
}

function checkText(check) {
  if (!check.ok) return t("c_failed");
  switch (check.rule) {
    case "card_luhn":
      return t("c_card_luhn", { brand: BRANDS[check.brand] ?? check.brand, length: check.length });
    case "phone_numbering_plan":
      return check.valid
        ? t("c_phone_valid", { region: check.region, line: lineLabel(check.line) })
        : t("c_phone_possible", { region: check.region });
    default:
      return t(`c_${check.rule}`, check);
  }
}

function flash(node) {
  node.classList.remove("d-flash");
  void node.offsetWidth;
  node.classList.add("d-flash");
}

function say(key) {
  ui.say.textContent = t(key);
  flash(ui.say);
}

// --- Policy toggles ------------------------------------------------------------------

function buildRules() {
  const rows = {};
  const list = el("div", { class: "pg-rules" });
  for (const type of setup.types) {
    const labelId = `pg-rule-${type}`;
    const inputs = {};
    const seg = el("div", { class: "pg-seg" });
    for (const action of setup.actions) {
      const input = el("input", {
        type: "radio",
        name: `pg-${type}`,
        value: action,
        checked: policy[type] === action,
        disabled: true,
      });
      input.addEventListener("change", () => {
        if (input.checked) policy[type] = action;
      });
      inputs[action] = input;
      seg.append(el("label", {}, input, el("span", { text: t(action) })));
    }
    const row = el(
      "div",
      { class: "pg-rule", role: "radiogroup", "aria-labelledby": labelId },
      el("span", { class: "pg-rule-name", id: labelId }, typeLabel(type), el("code", { text: type })),
      seg,
    );
    rows[type] = { row, inputs };
    list.append(row);
  }
  return { list, rows };
}

function setRule(type, action) {
  policy[type] = action;
  const rule = ui.rules.rows[type];
  rule.inputs[action].checked = true;
  flash(rule.row);
}

// --- Rendering results ---------------------------------------------------------------

function detectionRow(d) {
  let action;
  if (d.action === "mask") {
    action = d.placeholder
      ? el("span", { class: "pg-ph", text: d.placeholder })
      : el("span", { class: "d-note", text: t("a_mask_none") });
  } else if (d.action === "block") {
    action = el("span", { class: "d-badge fail", text: t("a_block") });
  } else {
    action = el("span", { class: "d-badge sim", text: t("a_allow") });
  }
  return el(
    "tr",
    { class: "d-enter" },
    el("td", { class: "pg-c-type", "data-label": t("colType") }, el("strong", { text: typeLabel(d.type) })),
    el("td", { class: "pg-c-value mono", "data-label": t("colValue"), text: d.value }),
    el(
      "td",
      { class: "pg-c-check", "data-label": t("colCheck") },
      el("span", { class: `pg-tick ${d.check.ok ? "ok" : "fail"}`, "aria-hidden": "true", text: d.check.ok ? "✓" : "✕" }),
      el("span", { text: checkText(d.check) }),
    ),
    el("td", { class: "pg-c-action", "data-label": t("colAction") }, action),
  );
}

async function showDetections(result, play, pace = 650) {
  ui.detBody.replaceChildren();
  ui.detTable.hidden = result.detections.length === 0;
  ui.detNote.textContent = result.detections.length ? "" : t("foundNone");
  ui.detNote.hidden = result.detections.length > 0;
  for (const d of result.detections) {
    ui.detBody.append(detectionRow(d));
    if (play) await play.wait(pace);
  }
}

function originalText(result) {
  return el(
    "p",
    { class: "pg-text d-enter" },
    result.original.map((piece) =>
      piece.kind
        ? el(
            "mark",
            { class: "pg-v", dataset: { action: piece.action }, title: `${typeLabel(piece.kind)} · ${t(piece.action)}` },
            el("small", { text: piece.kind }),
            piece.text,
          )
        : piece.text,
    ),
  );
}

function sentText(segments) {
  return el(
    "p",
    { class: "pg-text d-enter" },
    segments.map((s) => (s.token ? el("span", { class: "pg-ph", text: s.text }) : s.text)),
  );
}

function answerText(segments) {
  return el(
    "p",
    { class: "pg-text d-enter" },
    segments.map((s) =>
      s.token ? el("mark", { class: "pg-r", title: t("restored", { token: s.token }), text: s.text }) : s.text,
    ),
  );
}

function showVerdict(result) {
  let badge;
  let text;
  if (FAILED.includes(result.decision)) {
    badge = el("span", { class: "d-badge fail", text: t("d_error") });
    text = t(`err_${result.decision}`, { max: result.max_chars, error: result.error });
  } else {
    badge = el("span", { class: `d-badge ${DECISION_BADGE[result.decision]}`, text: t(`d_${result.decision}`) });
    if (result.decision === "blocked") {
      text = t("verdictBlocked", { types: result.blocked_types.map(typeLabel).join(", ") });
    } else if (result.decision === "masked") {
      text = t("verdictMasked", { n: result.placeholders, ms: result.latency_ms });
    } else {
      text = t("verdictPassed", { ms: result.latency_ms });
    }
  }
  ui.verdict.replaceChildren(badge, el("span", { text }));
  ui.verdict.hidden = false;
  flash(ui.verdict);
}

function showOriginal(result) {
  ui.p1.replaceChildren(originalText(result));
}

function showSent(result) {
  ui.p2meta.replaceChildren();
  if (result.decision === "blocked") {
    ui.p2.replaceChildren(el("p", { class: "pg-refused d-enter", text: t("refused") }));
    return;
  }
  const clean = result.values_in_request === 0;
  ui.p2meta.append(
    el("span", { class: `d-badge ${clean ? "ok" : "fail"}`, text: clean ? t("leakOk") : t("leakBad", { n: result.values_in_request }) }),
    el("span", { class: "d-badge", text: t("placeholders", { n: result.placeholders }) }),
  );
  ui.p2.replaceChildren(...result.sent.map(sentText));
}

function showAnswer(result) {
  if (result.decision === "blocked") {
    ui.p3.replaceChildren(el("p", { class: "pg-refused d-enter", text: t("noAnswer") }));
    return;
  }
  ui.p3.replaceChildren(
    answerText(result.answer),
    el(
      "details",
      { class: "pg-raw" },
      el("summary", { text: t("raw") }),
      el("pre", { class: "pg-text mono", text: result.llm_answer }),
    ),
  );
}

function showAudit(entries) {
  if (!entries.length) {
    ui.audit.replaceChildren(el("p", { class: "d-note", text: t("auditEmpty") }));
    return;
  }
  const time = (ts) =>
    new Date(ts).toLocaleTimeString(lang === "en" ? "en-GB" : lang, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  ui.audit.replaceChildren(
    el(
      "ul",
      { class: "d-log" },
      entries.map((e, i) =>
        el(
          "li",
          { class: i === 0 ? "d-enter" : null },
          el("time", { datetime: e.ts, text: time(e.ts) }),
          el(
            "div",
            { class: "pg-entry" },
            el(
              "div",
              { class: "d-row" },
              el("span", { class: `d-badge ${DECISION_BADGE[e.decision] ?? "fail"}`, text: t(`d_${e.decision}`) }),
              el("span", { text: e.summary }),
              el("span", { class: "d-note mono", text: e.latency_ms == null ? e.model : `${e.model} · ${e.latency_ms} ms` }),
            ),
            el("code", { class: "pg-json", text: JSON.stringify(e.entities) }),
          ),
        ),
      ),
    ),
  );
}

function clearPanels() {
  ui.p1.replaceChildren(el("p", { class: "d-note", text: t("empty1") }));
  ui.p2.replaceChildren(el("p", { class: "d-note", text: t("empty2") }));
  ui.p3.replaceChildren(el("p", { class: "d-note", text: t("empty3") }));
  ui.p2meta.replaceChildren();
}

/** Sends the message through the gateway and shows the result at once (visitor's turn). */
async function send() {
  if (busy) return;
  busy = true;
  ui.send.disabled = true;
  try {
    const result = await py.call("run", ui.input.value, { ...policy });
    showVerdict(result);
    if (FAILED.includes(result.decision)) {
      clearPanels();
      await showDetections({ detections: [] });
    } else {
      await showDetections(result);
      showOriginal(result);
      showSent(result);
      showAnswer(result);
    }
    showAudit(result.audit);
  } finally {
    busy = false;
    ui.send.disabled = false;
  }
}

// --- Layout --------------------------------------------------------------------------

function build() {
  Object.assign(policy, setup.policy);
  const input = el("textarea", { class: "d-textarea pg-input", id: "pg-input", rows: 6, maxlength: setup.max_chars, disabled: true, spellcheck: "false" });
  const send_ = el("button", { class: "d-btn solid", type: "button", disabled: true, text: t("send") });
  const samples = setup.samples.map((s) =>
    el("button", {
      class: "d-btn pg-chip",
      type: "button",
      disabled: true,
      text: t(`s_${s.id}`),
      onclick: () => {
        input.value = s.text;
        input.focus();
      },
    }),
  );
  const rules = buildRules();
  const detBody = el("tbody");
  const detTable = el(
    "table",
    { class: "d-table pg-dets", hidden: true },
    el(
      "thead",
      {},
      el("tr", {}, el("th", { text: t("colType") }), el("th", { text: t("colValue") }), el("th", { text: t("colCheck") }), el("th", { text: t("colAction") })),
    ),
    detBody,
  );
  const detNote = el("p", { class: "d-note", text: t("foundWait") });
  const detPanel = el("section", { class: "d-panel" }, el("h2", { class: "d-label", text: t("found") }), detNote, detTable);
  const p1 = el("div");
  const p2 = el("div");
  const p3 = el("div");
  const p2meta = el("div", { class: "d-row pg-meta" });
  const verdict = el("p", { class: "pg-verdict", hidden: true, role: "status" });
  const audit = el("div");
  const auditPanel = el(
    "section",
    { class: "d-panel" },
    el("h2", { class: "d-label", text: t("audit") }),
    el("p", { class: "d-note pg-gap", text: t("auditNote", { columns: setup.audit_columns.join(", ") }) }),
    audit,
  );
  const sayLine = el("p", { class: "pg-say", "aria-live": "polite" });
  const three = el(
    "div",
    { class: "pg-three" },
    el("section", { class: "d-panel" }, el("h2", { class: "d-label", text: t("p1") }), p1),
    el("section", { class: "d-panel" }, el("div", { class: "pg-head" }, el("h2", { class: "d-label", text: t("p2") }), p2meta), p2),
    el(
      "section",
      { class: "d-panel" },
      el("div", { class: "pg-head" }, el("h2", { class: "d-label", text: t("p3") }), el("span", { class: "d-badge sim", text: t("simBadge") })),
      el("p", { class: "d-note pg-gap", text: t("simNote") }),
      p3,
    ),
  );

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      send();
    }
  });
  send_.addEventListener("click", send);

  demo.stage.replaceChildren(
    el("div", { class: "pg-intro" }, el("p", { text: t("intro") }), sayLine),
    el(
      "div",
      { class: "d-cols wide-left" },
      el(
        "section",
        { class: "d-panel d-stack" },
        el("label", { class: "d-label", for: "pg-input", text: t("message") }),
        input,
        el("div", { class: "d-row" }, send_, el("span", { class: "d-note", text: t("shortcut") })),
        el("div", { class: "d-row pg-samples" }, el("span", { class: "d-note", text: `${t("samples")}:` }), samples),
        el("p", { class: "d-note", text: t("names", { file: "names.demo.txt", names: setup.names.join(", ") }) }),
      ),
      el(
        "section",
        { class: "d-panel" },
        el("h2", { class: "d-label", text: t("policy") }),
        el("p", { class: "d-note pg-gap", text: t("policyNote") }),
        rules.list,
      ),
    ),
    detPanel,
    verdict,
    three,
    auditPanel,
  );
  ui = { input, send: send_, samples, rules, detBody, detTable, detNote, detPanel, p1, p2, p3, p2meta, verdict, audit, auditPanel, three, say: sayLine };
  clearPanels();
  showAudit([]);
}

demo.autoplay({
  async reset() {
    await py.call("reset");
    build();
  },
  async script(play) {
    say("say1");
    await play.wait(1400);
    setRule("CARD", "mask");
    await play.wait(1600);

    say("say2");
    await play.type(ui.input, t("demoMessage"), { cps: 38 });
    await play.wait(700);

    say("say3");
    const masked = await py.call("run", ui.input.value, { ...policy });
    play.show(ui.detPanel);
    await showDetections(masked, play);
    await play.wait(900);

    say("say4");
    showVerdict(masked);
    showOriginal(masked);
    showSent(masked);
    play.show(ui.three);
    await play.wait(2600);

    say("say5");
    showAnswer(masked);
    await play.wait(2600);
    showAudit(masked.audit);
    await play.wait(1600);

    say("say6");
    setRule("CARD", "block");
    await play.wait(1800);
    const blocked = await py.call("run", ui.input.value, { ...policy });
    await showDetections(blocked, play, 200);
    showVerdict(blocked);
    showOriginal(blocked);
    showSent(blocked);
    showAnswer(blocked);
    play.show(ui.verdict);
    await play.wait(2200);

    say("say7");
    showAudit(blocked.audit);
    play.show(ui.auditPanel);
    await play.wait(2800);
  },
  interactive() {
    say("sayReady");
    ui.input.disabled = false;
    ui.send.disabled = false;
    for (const button of ui.samples) button.disabled = false;
    for (const { inputs } of Object.values(ui.rules.rows)) {
      for (const input of Object.values(inputs)) input.disabled = false;
    }
  },
});
