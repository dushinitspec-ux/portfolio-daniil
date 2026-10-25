// Live demo of projects/02-hotel-ai-concierge. Guests chat with the hotel's Telegram bot; a
// question the knowledge base does not answer goes to the reception group, and the staff
// reply comes back to the guest. Every bot text on screen comes from the project's Python
// code (app/web_demo.py -> Concierge with the offline MockLLM) running in Pyodide. Only the
// guests' questions and the staff answer are scripted, and both come from app/demo.py.
import { createDemo, el, lang, reducedMotion } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: (strings[lang] ?? strings.en).title, strings });
const { t } = demo;
const py = await demo.python();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, reducedMotion ? 0 : ms));
// Scripted pauses go through the player (Skip / Replay); the visitor's own messages get a
// short, fixed delay so the reply does not appear before the question.
const pause = (play, ms) => (play ? play.wait(ms) : sleep(Math.min(ms, 400)));

let info = null; // what start() returned: hotel, guests, script, suggestions
let ui = null; // DOM nodes of the current run
let state = null; // replaced on every run; stale async work checks `s !== state`

const initials = (name) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

const scrollDown = (chat) => {
  chat.scrollTop = chat.scrollHeight;
};

function bubble(kind, text, meta) {
  return el("div", { class: `d-msg ${kind} d-enter` }, text, meta ? el("span", { class: "meta", text: meta }) : null);
}

// Guest side

async function openGuest(id, play) {
  const s = state;
  const guest = s.guests.get(id);
  if (s.current !== id) {
    s.guests.get(s.current)?.tab.setAttribute("aria-selected", "false");
    guest.tab.setAttribute("aria-selected", "true");
    guest.dot.hidden = true;
    ui.chat.replaceWith(guest.chat);
    ui.chat = guest.chat;
    ui.sub.textContent = t("chatWith", { name: guest.name });
    ui.inputLabel.textContent = t("messageAs", { name: guest.name });
    s.current = id;
    scrollDown(guest.chat);
  }
  if (guest.welcomed) return;
  guest.welcomed = true;
  guest.chat.append(bubble("out", "/start"));
  await pause(play, 450);
  const reply = await py.call("welcome", id);
  if (s !== state) return;
  guest.chat.append(bubble("in", reply.text));
  scrollDown(guest.chat);
}

async function sendGuest(text, play) {
  const s = state;
  const guest = s.guests.get(s.current);
  guest.chat.append(bubble("out", text));
  scrollDown(guest.chat);
  await pause(play, 300);
  const typing = el("div", { class: "d-msg in hc-typing", text: t("typing") });
  guest.chat.append(typing);
  scrollDown(guest.chat);
  await pause(play, 650);

  let reply;
  try {
    reply = await py.call("ask", guest.id, text);
  } catch (error) {
    typing.remove();
    guest.chat.append(bubble("in hc-error", t("failed", { error: error.message })));
    return null;
  }
  typing.remove();
  if (s !== state) return null;
  const route = reply.escalated ? t("toStaff", { id: reply.escalation_id }) : t("fromKb");
  guest.chat.append(bubble("in", reply.text, `${reply.language.toUpperCase()} · ${route}`));
  scrollDown(guest.chat);
  if (s.current !== guest.id) guest.dot.hidden = false; // the visitor switched chats meanwhile
  if (reply.escalated) addStaffQuestion(s, guest, reply);
  await refreshStats(s);
  return reply;
}

function setBusy(s, busy) {
  s.busy = busy;
  const off = busy || !s.interactive;
  ui.send.disabled = off;
  for (const button of ui.suggestions) button.disabled = off;
}

async function submitGuest(text) {
  const s = state;
  const value = (text ?? ui.input.value).trim();
  if (!value || s.busy || !s.interactive) return;
  ui.input.value = "";
  setBusy(s, true);
  await sendGuest(value);
  if (s === state) setBusy(s, false);
}

// Staff side

function addStaffQuestion(s, guest, reply) {
  ui.staffEmpty?.remove();
  ui.staffEmpty = null;
  const entry = { reply, guest, button: null };
  entry.button = el("button", {
    class: "d-btn",
    type: "button",
    "aria-pressed": "false",
    text: t("replyTo", { id: reply.escalation_id }),
    disabled: !s.interactive,
    onclick: () => selectTarget(s, entry, true),
  });
  s.staffItems.push(entry);
  ui.staffChat.append(
    el("div", { class: "d-msg in d-enter d-flash" }, reply.staff_text, el("span", { class: "meta", text: t("toGroup") })),
    el("div", { class: "d-keys hc-keys" }, entry.button),
  );
  scrollDown(ui.staffChat);
  return entry;
}

function selectTarget(s, entry, focus = false) {
  if (s !== state) return;
  s.target = entry;
  for (const item of s.staffItems) item.button.setAttribute("aria-pressed", String(item === entry));
  ui.target.textContent = t("replyingTo", { id: entry.reply.escalation_id, name: entry.guest.name });
  if (s.interactive) {
    ui.staffInput.disabled = false;
    ui.staffSend.disabled = false;
    if (focus) ui.staffInput.focus();
  }
}

async function sendStaff(text, play) {
  const s = state;
  const entry = s.target;
  if (!entry) return;
  ui.staffChat.append(bubble("out", text, t("staffMeta", { id: entry.reply.escalation_id })));
  scrollDown(ui.staffChat);
  await pause(play, 600);

  let result;
  try {
    result = await py.call("staff_reply", entry.reply.staff_message_id, text);
  } catch (error) {
    ui.staffChat.append(bubble("in hc-error", t("failed", { error: error.message })));
    return;
  }
  if (s !== state || !result.delivered) return;
  ui.staffChat.append(bubble("in", result.confirmation));
  scrollDown(ui.staffChat);
  await pause(play, 500);

  const guest = s.guests.get(result.guest);
  const delivered = bubble("in", result.guest_text, t("toGuest", { name: guest.name }));
  guest.chat.append(delivered);
  if (result.needs_translation && !result.translated) {
    guest.chat.append(
      el(
        "div",
        { class: "hc-note d-enter" },
        el("span", { class: "d-badge sim", text: t("offlineModel") }),
        el("span", { text: t("noTranslation", { language: t(`lang_${result.language}`) }) }),
      ),
    );
  }
  scrollDown(guest.chat);
  if (s.current !== guest.id) guest.dot.hidden = false;
  await refreshStats(s);
  return delivered;
}

async function submitStaff() {
  const s = state;
  const value = ui.staffInput.value.trim();
  if (!value || s.busy || !s.interactive || !s.target) return;
  ui.staffInput.value = "";
  s.busy = true;
  ui.staffSend.disabled = true;
  await sendStaff(value);
  if (s !== state) return;
  s.busy = false;
  ui.staffSend.disabled = false;
}

async function refreshStats(s) {
  const stats = await py.call("stats");
  if (s !== state) return;
  ui.stats.questions.textContent = stats.questions;
  ui.stats.bot.textContent = stats.answered_by_bot;
  ui.stats.staff.textContent = stats.escalated;
  ui.stats.open.textContent = stats.open_escalations;
}

// The page

function build() {
  const s = { guests: new Map(), current: null, staffItems: [], target: null, busy: false, interactive: false };
  for (const guest of info.guests) {
    const dot = el("span", { class: "hc-dot", title: t("unread"), hidden: true });
    const tab = el(
      "button",
      { class: "d-btn hc-tab", type: "button", role: "tab", "aria-selected": "false", disabled: true },
      el("span", { text: `${guest.name.split(" ")[0]} · ${guest.telegram_language.toUpperCase()}` }),
      dot,
    );
    tab.addEventListener("click", () => {
      if (state === s && s.interactive) openGuest(guest.id);
    });
    const chat = el("div", { class: "d-chat", role: "log", "aria-live": "polite" });
    s.guests.set(guest.id, { ...guest, tab, dot, chat, welcomed: false });
  }
  const first = s.guests.values().next().value;

  const n = {};
  n.chat = first.chat;
  n.sub = el("div", { class: "sub", text: t("chatWith", { name: first.name }) });
  n.input = el("input", {
    class: "d-input",
    id: "hc-guest-input",
    type: "text",
    autocomplete: "off",
    maxlength: "1000",
    placeholder: t("placeholder"),
    disabled: true,
  });
  n.inputLabel = el("label", { class: "hc-sr", for: "hc-guest-input", text: t("messageAs", { name: first.name }) });
  n.send = el("button", { class: "d-btn solid", type: "submit", text: t("send"), disabled: true });
  const guestPhone = el(
    "section",
    { class: "d-phone hc-guest", "aria-label": t("guestChats") },
    el(
      "div",
      { class: "d-phone-head" },
      el("div", { class: "d-avatar", text: initials(info.hotel) }),
      el("div", { class: "hc-head-text" }, el("div", { class: "name", text: t("botName", { hotel: info.hotel }) }), n.sub),
      el("span", { class: "d-badge sim", text: t("offlineModel") }),
    ),
    n.chat,
    el(
      "form",
      {
        class: "d-composer",
        onsubmit: (event) => {
          event.preventDefault();
          submitGuest();
        },
      },
      n.inputLabel,
      n.input,
      n.send,
    ),
  );
  first.tab.setAttribute("aria-selected", "true");
  s.current = first.id;

  const ordered = [...info.suggestions].sort((a, b) => (b.lang === lang) - (a.lang === lang));
  n.suggestions = ordered.map((item) =>
    el("button", { class: "d-btn", type: "button", lang: item.lang, text: item.text, disabled: true, onclick: () => submitGuest(item.text) }),
  );

  n.staffChat = el("div", { class: "d-chat", role: "log", "aria-live": "polite" });
  n.staffEmpty = el("p", { class: "hc-empty", text: t("staffEmpty") });
  n.staffChat.append(n.staffEmpty);
  n.target = el("label", { class: "hc-target", for: "hc-staff-input", text: t("pickQuestion") });
  n.staffInput = el("input", {
    class: "d-input",
    id: "hc-staff-input",
    type: "text",
    autocomplete: "off",
    maxlength: "1000",
    placeholder: t("staffPlaceholder"),
    disabled: true,
  });
  n.staffSend = el("button", { class: "d-btn solid", type: "submit", text: t("send"), disabled: true });
  n.staffPhone = el(
    "section",
    { class: "d-phone hc-staff", "aria-label": t("staffGroup") },
    el(
      "div",
      { class: "d-phone-head" },
      el("div", { class: "d-avatar", text: "R" }),
      el("div", { class: "hc-head-text" }, el("div", { class: "name", text: t("staffGroup") }), el("div", { class: "sub", text: t("staffSub") })),
    ),
    n.staffChat,
    el(
      "div",
      { class: "hc-staff-composer" },
      n.target,
      el(
        "form",
        {
          class: "d-composer",
          "aria-label": t("replyAs"),
          onsubmit: (event) => {
            event.preventDefault();
            submitStaff();
          },
        },
        n.staffInput,
        n.staffSend,
      ),
    ),
  );

  const stat = (label) => {
    const value = el("strong", { text: "0" });
    return [value, el("div", {}, value, el("span", { text: label }))];
  };
  const [questions, questionsCell] = stat(t("statQuestions"));
  const [bot, botCell] = stat(t("statBot"));
  const [staff, staffCell] = stat(t("statStaff"));
  const [open, openCell] = stat(t("statOpen"));
  n.stats = { questions, bot, staff, open };

  demo.stage.replaceChildren(
    el("p", { class: "d-note", text: t("intro") }),
    el(
      "div",
      { class: "d-cols" },
      el(
        "div",
        { class: "d-stack hc-col" },
        el("span", { class: "d-label", text: t("guestChats") }),
        el("div", { class: "hc-tabs", role: "tablist", "aria-label": t("guestChats") }, [...s.guests.values()].map((g) => g.tab)),
        guestPhone,
        el(
          "div",
          { class: "d-stack hc-suggest" },
          el("span", { class: "d-label", text: t("suggestTitle") }),
          el("div", { class: "d-keys" }, n.suggestions),
        ),
      ),
      el(
        "div",
        { class: "d-stack hc-col" },
        el("span", { class: "d-label", text: t("staffColumn") }),
        n.staffPhone,
        el("div", { class: "d-panel" }, el("span", { class: "d-label", text: t("statsTitle") }), el("div", { class: "hc-stats" }, questionsCell, botCell, staffCell, openCell)),
      ),
    ),
    el(
      "div",
      { class: "d-panel d-stack" },
      el("span", { class: "d-label", text: t("howTitle") }),
      el("p", { class: "d-note", text: t("how") }),
      el("p", { class: "d-note", text: t("kbTopics", { n: info.sections.length, list: info.sections.join(" · ") }) }),
    ),
  );
  ui = n;
  state = s;
}

demo.autoplay({
  async reset() {
    state = null;
    info = await py.call("start");
    build();
  },
  async script(play) {
    const s = state;
    let escalation = null;
    for (const item of info.script) {
      await openGuest(item.guest, play);
      await play.wait(700);
      await play.type(ui.input, item.text);
      await play.wait(250);
      ui.input.value = "";
      const reply = await sendGuest(item.text, play);
      if (reply?.escalated) escalation = s.staffItems.at(-1);
      await play.wait(reply?.escalated ? 1200 : 2300);
    }
    if (!escalation) return;
    play.show(ui.staffPhone);
    selectTarget(s, escalation);
    await play.wait(1000);
    await play.type(ui.staffInput, info.staff_answer, { cps: 40 });
    await play.wait(300);
    ui.staffInput.value = "";
    const delivered = await sendStaff(info.staff_answer, play);
    if (delivered) play.show(delivered);
    await play.wait(2500);
  },
  interactive() {
    const s = state;
    s.interactive = true;
    for (const guest of s.guests.values()) guest.tab.disabled = false;
    ui.input.disabled = false;
    for (const item of s.staffItems) item.button.disabled = false;
    if (s.target) {
      ui.staffInput.disabled = false;
      ui.staffSend.disabled = false;
    }
    setBusy(s, false);
  },
});
