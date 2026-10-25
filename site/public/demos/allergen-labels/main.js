// Allergen Labels in the browser: the project's real dictionary matcher, Kitchen service
// (confirmation rules, append-only log) and menu builder run in Pyodide (app/web_demo.py).
// Every analysis, state and menu line shown here comes from py.call(); this file lays it out.
import { createDemo, el } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: "Allergen Labels demo", strings });
const { t, lang } = demo;
const py = await demo.python();

const MENU_LANGS = ["en", "ru", "tr", "de"];
const STATE_BADGE = { new: "warn", confirmed: "ok", changed: "fail", review: "warn", archived: "sim" };
const STATUS_BADGE = { found: "", none: "ok", check: "warn" };
const locale = lang === "en" ? "en-GB" : lang;

let meta = null;
let ui = {};
let current = null; // the saved dish being edited, or null for a new one
let lastCheck = null;
let menuLang = "en";
let fresh = new Set(); // dish ids the visitor (or the autoplay) put on the menu
let flashIds = new Set(); // ... and those that only just got there
let checkTimer = null;
let checkRun = 0;

const allergen = (n) => meta.allergens[n - 1];
const label = (n) => allergen(n).label[lang];
const dishName = (names) => names[lang] || names.en;
const when = (iso) => new Date(iso).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function flash(node) {
  node.classList.remove("d-flash");
  void node.offsetWidth;
  node.classList.add("d-flash");
}

function say(key) {
  ui.say.textContent = t(key);
  flash(ui.say);
}

function message(node, text, kind = "") {
  node.replaceChildren(text ? el("span", { class: `al-msg ${kind}`, text }) : "");
  if (text) flash(node);
}

// Known error messages of the Kitchen service (app/service.py), shown in the page language.
function errorText(error, stale) {
  if (stale) return t("errStale");
  if (error.startsWith("Enter your name: a confirmation")) return t("errNameConfirm");
  if (error.startsWith("Enter your name")) return t("errName");
  if (error.startsWith("The dish needs at least an English name")) return t("errNameEn");
  if (error.startsWith("List the ingredients")) return t("errRecipe");
  return error;
}

function chip(n, certain = true) {
  return el(
    "span",
    { class: `al-chip${certain ? "" : " maybe"}`, title: allergen(n).name[lang] },
    el("b", { text: String(n) }),
    certain ? label(n) : `${label(n)}?`,
  );
}

// --- Dictionary check ----------------------------------------------------------------

function itemRow(item) {
  const why = el("div", { class: "al-why" });
  for (const hit of item.hits) {
    why.append(
      el(
        "div",
        { class: "al-hit" },
        chip(hit.allergen, hit.certain),
        el("span", { class: "d-note", text: t("matched", { term: hit.found, language: hit.language.toUpperCase() }) }),
      ),
    );
  }
  if (item.unknown.length) why.append(el("div", { class: "al-unknown", text: t("unknownWords", { words: item.unknown.join(", ") }) }));
  for (const note of item.notes) why.append(el("div", { class: "al-note", text: note }));
  const name = el("td", { class: "al-c-name" });
  if (item.parent) name.append(el("span", { class: "al-parent", text: `${item.parent} › ` }));
  name.append(el("strong", { text: item.text }));
  return el(
    "tr",
    { class: `d-enter${item.status === "check" ? " al-row-check" : ""}` },
    name,
    el("td", { class: "al-c-status" }, el("span", { class: `d-badge ${STATUS_BADGE[item.status]}`, text: t(`st_${item.status}`) })),
    el("td", {}, why),
  );
}

function renderCheck(result) {
  lastCheck = result;
  if (!result || !result.items.length) {
    ui.checkBody.replaceChildren(el("p", { class: "d-note", text: t("checkEmpty") }));
    ui.willReset.hidden = true;
    return;
  }
  const summary = el(
    "div",
    { class: "al-summary" },
    el("span", { class: "d-label", text: t("summary") }),
    result.allergens.length
      ? el("span", { class: "al-chips" }, result.allergens.map((n) => chip(n, result.certain.includes(n))))
      : el("span", { text: t("summaryNone") }),
    result.to_check.length ? el("span", { class: "d-badge warn", text: t("toCheck", { n: result.to_check.length }) }) : null,
  );
  const table = el(
    "table",
    { class: "d-table al-items" },
    el("thead", {}, el("tr", {}, el("th", { text: t("colIngredient") }), el("th", { text: t("colResult") }), el("th", { text: t("colAllergens") }))),
    el("tbody", {}, result.items.map(itemRow)),
  );
  ui.checkBody.replaceChildren(summary, table, el("p", { class: "d-note", text: t("maybeKey") }));
  ui.willReset.hidden = !(current && current.confirmation && result.hash !== current.recipe_hash);
}

async function refreshCheck() {
  const run = ++checkRun;
  const recipe = ui.recipe.value;
  const result = recipe.trim() ? await py.call("check", recipe) : null;
  if (run === checkRun) renderCheck(result);
  return result;
}

// --- Confirmation and log ------------------------------------------------------------

function reasons(item) {
  const out = [];
  if (item.unknown.length) out.push(t("why_unknown"));
  const maybe = item.hits.filter((h) => !h.certain).map((h) => `${h.allergen} ${label(h.allergen)}`);
  if (maybe.length) out.push(t("why_usually", { list: maybe.join(", ") }));
  if (item.free_from) out.push(t("why_free"));
  return out.join("; ");
}

function eventDetail(e) {
  if (e.action === "confirmation reset") return t("evResetDetail");
  if (e.action === "confirmed") return t("evAllergens", { list: e.detail.replace(/^allergens: /, "") });
  if (e.action === "details edited") return "";
  return e.detail;
}

function renderLog() {
  if (!current) {
    ui.log.replaceChildren(el("p", { class: "d-note", text: t("logEmpty") }));
    return;
  }
  ui.log.replaceChildren(
    el(
      "ul",
      { class: "d-log" },
      current.events.map((e, i) =>
        el(
          "li",
          { class: i === 0 ? "d-enter" : null },
          el("time", { datetime: e.at, text: new Date(e.at).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }),
          el(
            "div",
            {},
            el("strong", { text: t(`ev_${e.action}`) === `ev_${e.action}` ? e.action : t(`ev_${e.action}`) }),
            el("span", { class: "d-note", text: ` · ${e.actor}` }),
            eventDetail(e) ? el("div", { class: "al-note", text: eventDetail(e) }) : null,
          ),
        ),
      ),
    ),
  );
}

function renderConfirm() {
  renderLog();
  if (!current) {
    ui.confirmBody.replaceChildren(el("p", { class: "d-note", text: t("confirmFirst") }));
    return;
  }
  const status = el(
    "div",
    { class: "al-state" },
    el("span", { class: `d-badge ${STATE_BADGE[current.state]}`, text: t(`short_${current.state}`) }),
    el("strong", { text: t(`state_${current.state}`) }),
  );
  const who = current.confirmation
    ? el("p", { class: "d-note", text: t("confirmedBy", { name: current.confirmation.by, when: when(current.confirmation.at) }) })
    : current.last_confirmation
      ? el("p", { class: "d-note", text: t("lastConfirmedBy", { name: current.last_confirmation.by, when: when(current.last_confirmation.at) }) })
      : null;

  const toCheck = current.analysis.items.filter((i) => i.status === "check");
  const needs = el(
    "div",
    { class: "al-needs" },
    el("h3", { class: "d-label", text: t("needsPerson") }),
    toCheck.length
      ? el("ul", {}, toCheck.map((i) => el("li", {}, el("strong", { text: i.label }), el("span", { class: "d-note", text: ` · ${reasons(i)}` }))))
      : el("p", { class: "d-note", text: t("needsNone") }),
  );

  ui.boxes = {};
  const grid = el("div", { class: "al-boxes" });
  for (const a of meta.allergens) {
    const box = el("input", { type: "checkbox", value: a.number, checked: current.preselected.includes(a.number), disabled: ui.locked });
    ui.boxes[a.number] = box;
    grid.append(
      el(
        "label",
        { class: `al-box${current.suggested.includes(a.number) ? " sug" : ""}`, title: a.name[lang] },
        box,
        el("b", { text: String(a.number) }),
        el("span", { text: a.label[lang] }),
      ),
    );
  }
  const confirmButton = el("button", { class: "d-btn solid", type: "button", text: t("confirm"), disabled: ui.locked, onclick: () => confirmDish() });
  ui.confirmButton = confirmButton;
  ui.signed = el("span", { class: "d-note" });
  updateSigned();
  ui.confirmBody.replaceChildren(
    ...[status, who].filter(Boolean),
    needs,
    el("fieldset", { class: "al-pick" }, el("legend", { class: "d-label", text: t("pick") }), el("p", { class: "d-note", text: t("pickNote") }), grid),
    el("div", { class: "d-row" }, confirmButton, ui.signed),
    ui.confirmMsg,
  );
}

function updateSigned() {
  if (!ui.signed) return;
  const name = ui.chef.value.trim();
  ui.signed.textContent = name ? t("confirmAs", { name }) : t("confirmNoName");
}

// --- Menu card -----------------------------------------------------------------------

async function renderMenu() {
  const menu = await py.call("menu", menuLang);
  for (const [code, button] of Object.entries(ui.langButtons)) button.setAttribute("aria-pressed", String(code === menu.language));
  const sections = menu.sections.map((s) =>
    el(
      "section",
      { class: "al-menu-section" },
      el("h4", { text: s.title }),
      s.dishes.map((d) =>
        el(
          "div",
          { class: `al-dish${fresh.has(d.id) ? " al-fresh" : ""}${flashIds.has(d.id) ? " d-flash" : ""}` },
          el("span", { class: "al-dish-name" }, d.name, d.translated ? null : el("abbr", { class: "al-en", title: t("englishOnly"), text: "EN" })),
          el("span", { class: "al-fill", "aria-hidden": "true" }),
          d.allergens.length
            ? el("span", { class: "al-nums" }, d.allergens.map((n) => el("span", { text: String(n) })))
            : el("span", { class: "al-none", text: menu.text.none }),
        ),
      ),
    ),
  );
  const sheet = el(
    "article",
    { class: "al-sheet", lang: menu.language },
    el("div", { class: "al-mast" }, el("h3", { text: menu.title }), el("span", { text: menu.text.menu })),
    el("p", { class: "al-sample", text: menu.text.sample }),
    sections,
    el(
      "section",
      { class: "al-legend" },
      el("h4", { text: menu.text.allergens }),
      el("p", { text: menu.text.legend_intro }),
      el(
        "ol",
        {},
        menu.legend.map((line) =>
          el("li", {}, el("span", { class: "al-n", text: String(line.number) }), el("span", {}, el("strong", { text: line.label }), line.detail ? el("span", { class: "al-full", text: ` — ${line.detail}` }) : null)),
        ),
      ),
      el("div", { class: "al-foot" }, el("strong", { text: menu.text.ask_staff }), el("span", { text: menu.text.checked })),
    ),
  );
  ui.sheetWrap.replaceChildren(sheet);
  flashIds.clear();
  ui.hidden.textContent = menu.hidden.length ? t("hiddenNote", { names: menu.hidden.join(", ") }) : "";
  ui.hidden.hidden = !menu.hidden.length;
}

async function setMenuLang(code) {
  menuLang = code;
  await renderMenu();
}

// --- Dish form -----------------------------------------------------------------------

function fillOptions(dishes) {
  ui.select.replaceChildren(
    el("option", { value: "new", text: t("newDish") }),
    ...dishes.map((d) => el("option", { value: d.id, text: `${dishName(d.names)} · ${t(`short_${d.state}`)}` })),
  );
  ui.select.value = current ? String(current.id) : "new";
}

function fillForm(dish) {
  ui.nameEn.value = dish?.names.en ?? "";
  for (const code of ["ru", "tr", "de"]) ui.names[code].value = dish?.names[code] ?? "";
  ui.section.value = dish?.section ?? "mains";
  ui.recipe.value = dish?.recipe ?? "";
  ui.save.textContent = dish ? t("save") : t("add");
  message(ui.saveMsg, "");
  message(ui.confirmMsg, "");
}

async function openDish(value) {
  current = value === "new" ? null : await py.call("dish", Number(value));
  fillForm(current);
  renderConfirm();
  await refreshCheck();
}

async function saveDish() {
  const names = { en: ui.nameEn.value, ru: ui.names.ru.value, tr: ui.names.tr.value, de: ui.names.de.value };
  const result = await py.call("save", current ? current.id : null, names, ui.section.value, ui.recipe.value, ui.chef.value);
  if (!result.ok) {
    message(ui.saveMsg, errorText(result.error), "fail");
    return result;
  }
  const created = !current;
  current = result.dish;
  fresh.delete(current.id);
  fillOptions(result.dishes);
  ui.save.textContent = t("save");
  message(ui.confirmMsg, "");
  message(ui.saveMsg, created ? t("created") : result.reset ? t("resetMsg") : t("saved"), result.reset ? "fail" : "ok");
  renderConfirm();
  renderCheck(await py.call("check", ui.recipe.value));
  await renderMenu();
  return result;
}

async function confirmDish() {
  if (!current) return null;
  const numbers = Object.entries(ui.boxes).filter(([, box]) => box.checked).map(([n]) => Number(n));
  // The confirmation is for the recipe on screen; the service refuses it if that is not the saved one.
  const { hash } = await py.call("check", ui.recipe.value);
  const result = await py.call("confirm", current.id, numbers, ui.chef.value, hash);
  if (!result.ok) {
    message(ui.confirmMsg, errorText(result.error, result.stale), "fail");
    return result;
  }
  current = result.dish;
  fresh.add(current.id);
  flashIds.add(current.id);
  fillOptions(result.dishes);
  renderConfirm();
  message(ui.confirmMsg, t("confirmedMsg"), "ok");
  await renderMenu();
  return result;
}

function setLocked(locked) {
  ui.locked = locked;
  for (const node of [ui.chef, ui.select, ui.nameEn, ui.section, ui.recipe, ui.save, ...Object.values(ui.names), ...Object.values(ui.langButtons), ui.print]) {
    node.disabled = locked;
  }
  if (ui.confirmButton) ui.confirmButton.disabled = locked;
  for (const box of Object.values(ui.boxes ?? {})) box.disabled = locked;
}

// --- Layout --------------------------------------------------------------------------

function field(id, text, control) {
  return el("div", { class: "d-field" }, el("label", { class: "d-label", for: id, text }), control);
}

function build() {
  const chef = el("input", { class: "d-input", id: "al-chef", autocomplete: "name", maxlength: 80 });
  const select = el("select", { class: "d-select", id: "al-dish" });
  const nameEn = el("input", { class: "d-input", id: "al-name-en", maxlength: 120 });
  const names = Object.fromEntries(["ru", "tr", "de"].map((code) => [code, el("input", { class: "d-input", id: `al-name-${code}`, maxlength: 120, lang: code })]));
  const section = el("select", { class: "d-select", id: "al-section" }, meta.sections.map((s) => el("option", { value: s.id, text: s.label[lang] })));
  const recipe = el("textarea", { class: "d-textarea", id: "al-recipe", rows: 4, spellcheck: "false" });
  const save = el("button", { class: "d-btn solid", type: "button", text: t("add") });
  const saveMsg = el("div", { class: "al-msgline", role: "status" });
  const confirmMsg = el("div", { class: "al-msgline", role: "status" });
  const willReset = el("p", { class: "al-will-reset", hidden: true, text: t("willReset") });
  const checkBody = el("div");
  const confirmBody = el("div", { class: "d-stack" });
  const log = el("div");
  const sheetWrap = el("div", { class: "al-sheet-wrap" });
  const hidden = el("p", { class: "al-hidden", hidden: true });
  const langButtons = Object.fromEntries(
    MENU_LANGS.map((code) => [code, el("button", { class: "d-btn al-lang", type: "button", "aria-pressed": "false", lang: code, text: code.toUpperCase(), title: t(`lang_${code}`), onclick: () => setMenuLang(code) })]),
  );
  const print = el("button", { class: "d-btn", type: "button", text: t("print"), onclick: () => window.print() });
  const details = el(
    "details",
    { class: "al-names", open: true },
    el("summary", { class: "d-label", text: t("otherNames") }),
    el("div", { class: "al-names-grid" }, ["ru", "tr", "de"].map((code) => field(`al-name-${code}`, t(`lang_${code}`), names[code]))),
  );

  const recipePanel = el(
    "section",
    { class: "d-panel d-stack" },
    el("h2", { class: "d-label", text: t("recipePanel") }),
    field("al-dish", t("dish"), select),
    field("al-name-en", t("nameEn"), nameEn),
    details,
    field("al-section", t("section"), section),
    field("al-recipe", t("ingredients"), recipe),
    el("p", { class: "d-note", text: t("ingredientsHint") }),
    willReset,
    el("div", { class: "d-row" }, save),
    saveMsg,
  );
  const checkPanel = el(
    "section",
    { class: "d-panel" },
    el("div", { class: "al-head" }, el("h2", { class: "d-label", text: t("checkPanel") }), el("span", { class: "d-badge sim", text: t("noAi") })),
    checkBody,
  );
  const confirmPanel = el("section", { class: "d-panel" }, el("h2", { class: "d-label", text: t("confirmPanel") }), confirmBody);
  const logPanel = el("section", { class: "d-panel" }, el("h2", { class: "d-label", text: t("log") }), log);
  const menuPanel = el(
    "section",
    { class: "d-panel al-menu-panel" },
    el(
      "div",
      { class: "al-head" },
      el("h2", { class: "d-label", text: t("menuPanel") }),
      el("div", { class: "d-row al-langs", role: "group", "aria-label": t("menuLang") }, Object.values(langButtons), print),
    ),
    sheetWrap,
    hidden,
  );
  const sayLine = el("p", { class: "al-say", "aria-live": "polite" });

  demo.stage.replaceChildren(
    el(
      "div",
      { class: "al-intro" },
      el("p", { text: t("intro") }),
      el("div", { class: "d-row" }, el("span", { class: "d-badge sim", text: t("noAi") }), el("span", { class: "d-badge sim", text: t("sampleBadge") })),
      el("p", { class: "d-note", text: t("noAiNote") }),
      sayLine,
    ),
    el("section", { class: "d-panel al-chef" }, field("al-chef", t("chef"), chef), el("p", { class: "d-note", text: t("chefNote") })),
    el("div", { class: "d-cols" }, recipePanel, checkPanel),
    el("div", { class: "d-cols wide-left" }, confirmPanel, logPanel),
    menuPanel,
  );

  ui = { chef, select, nameEn, names, section, recipe, save, saveMsg, confirmMsg, willReset, checkBody, confirmBody, log, sheetWrap, hidden, langButtons, print, details, recipePanel, checkPanel, confirmPanel, menuPanel, say: sayLine, boxes: {}, locked: true };

  chef.addEventListener("input", updateSigned);
  select.addEventListener("change", () => openDish(select.value));
  recipe.addEventListener("input", () => {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(refreshCheck, 200);
  });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await saveDish();
    } finally {
      save.disabled = ui.locked;
    }
  });
  fillOptions(meta.dishes);
  fillForm(null);
  renderCheck(null);
  renderConfirm();
  setLocked(true);
}

async function typeDish(play, dish) {
  current = null;
  ui.select.value = "new";
  fillForm(null);
  renderConfirm();
  renderCheck(null);
  play.show(ui.recipePanel);
  await play.type(ui.nameEn, dish.names.en, { cps: 26 });
  for (const code of ["ru", "tr", "de"]) await play.type(ui.names[code], dish.names[code], { cps: 70 });
  ui.section.value = dish.section;
  flash(ui.section);
  await play.wait(300);
  await play.type(ui.recipe, dish.recipe, { cps: 30 });
  await refreshCheck();
}

demo.autoplay({
  async reset() {
    demo.stage.replaceChildren(el("p", { class: "d-note", text: t("preparing") }));
    meta = await py.call("setup", -new Date().getTimezoneOffset());
    current = null;
    fresh = new Set();
    flashIds = new Set();
    menuLang = "en";
    build();
    await renderMenu();
  },
  async script(play) {
    const [carbonara, satay] = meta.script;
    say("say1");
    await play.wait(1200);
    await play.type(ui.chef, t("demoChef"), { cps: 18 });
    updateSigned();
    await play.wait(300);

    await typeDish(play, carbonara);
    play.show(ui.checkPanel);
    await play.wait(1400);
    say("say2");
    for (const row of ui.checkBody.querySelectorAll(".al-row-check")) flash(row);
    await play.wait(2800);

    await saveDish();
    play.show(ui.confirmPanel);
    await play.wait(1600);
    say("say3");
    await play.wait(2800);
    await confirmDish();
    await play.wait(1200);
    say("say4");
    play.show(ui.menuPanel);
    await play.wait(2600);

    await typeDish(play, satay);
    play.show(ui.checkPanel);
    await play.wait(800);
    say("say5");
    for (const row of ui.checkBody.querySelectorAll(".al-row-check")) flash(row);
    await play.wait(3600);
    await saveDish();
    play.show(ui.confirmPanel);
    await play.wait(1400);
    await confirmDish();

    say("say6");
    play.show(ui.menuPanel);
    await play.wait(1800);
    for (const code of ["tr", "de", "ru"]) {
      await setMenuLang(code);
      await play.wait(1900);
    }
    if (lang !== "ru") {
      await setMenuLang(lang);
      await play.wait(900);
    }

    say("say7");
    play.show(ui.recipePanel);
    await play.type(ui.recipe, satay.changed_recipe, { cps: 50 });
    await refreshCheck();
    await play.wait(1800);
    await saveDish();
    say("say8");
    play.show(ui.confirmPanel);
    await play.wait(3000);
    play.show(ui.menuPanel);
    await play.wait(1500);
  },
  interactive() {
    setLocked(false);
    say("sayReady");
  },
});
