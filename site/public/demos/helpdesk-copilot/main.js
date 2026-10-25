// Live demo of projects/06-helpdesk-copilot. An employee chats with the IT bot; next to the
// chat, what the copilot did: BM25 top sources with scores, the confidence check against its
// thresholds, the decision, and the IT team's ticket queue. Every bot text and number on
// screen comes from the project's Python code (app/web_demo.py -> Copilot in demo mode)
// running in Pyodide. Only the employee's questions are scripted (app/web_demo.py SCRIPT).
import { createDemo, el, lang, reducedMotion } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: (strings[lang] ?? strings.en).title, strings });
const { t } = demo;
const py = await demo.python();

// The inline keyboard under an answer, labelled as in app/bot.py (feedback_keyboard).
const SOLVED_BUTTON = "✅ Solved";
const TICKET_BUTTON = "🎫 Create ticket";
const PRIORITY_BADGE = { P1: "d-badge solid", P2: "d-badge fail", P3: "d-badge warn", P4: "d-badge" };

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, reducedMotion ? 0 : ms));
// Scripted pauses go through the player (Skip / Replay); the visitor's own messages get a
// short delay so the reply does not appear before the question.
const pause = (play, ms) => (play ? play.wait(ms) : sleep(Math.min(ms, 400)));

let info = null; // what start() returned
let ui = null; // DOM nodes of the current run
let state = null; // replaced on every run; stale async work checks `s !== state`

const scrollDown = () => {
  ui.chat.scrollTop = ui.chat.scrollHeight;
};

function bubble(kind, text) {
  return el("div", { class: `d-msg ${kind} d-enter` }, text);
}

function fail(error) {
  ui.chat.append(bubble("in hd-error", t("failed", { error: error.message })));
  scrollDown();
}

// The chat

async function sendMessage(text, play) {
  const s = state;
  ui.chat.append(bubble("out", text));
  scrollDown();
  await pause(play, 300);
  const typing = el("div", { class: "d-msg in hd-typing", text: t("typing") });
  ui.chat.append(typing);
  scrollDown();
  await pause(play, 600);

  let reply;
  try {
    reply = await py.call("send", text);
  } catch (error) {
    typing.remove();
    fail(error);
    return null;
  }
  typing.remove();
  if (s !== state) return null;
  const message = bubble("in", reply.text);
  ui.chat.append(message);
  if (reply.kind === "answer" && reply.buttons) addKeyboard(s, reply);
  scrollDown();
  if (reply.kind === "answer") renderWork(reply);
  if (reply.kind === "ticket") renderDirect(reply);
  if (reply.ticket) await renderQueue(s, reply.ticket.id, reply.it_notification);
  else await renderQueue(s);
  return reply;
}

function addKeyboard(s, reply) {
  const solved = el("button", { class: "d-btn", type: "button", text: SOLVED_BUTTON, disabled: !s.interactive });
  const ticket = el("button", { class: "d-btn", type: "button", text: TICKET_BUTTON, disabled: !s.interactive });
  const keys = el("div", { class: "d-keys hd-keys" }, solved, ticket);
  const entry = { keys, solved, ticket, reply };
  solved.addEventListener("click", () => press(s, entry, "solved"));
  ticket.addEventListener("click", () => press(s, entry, "ticket"));
  s.keyboards.push(entry);
  ui.chat.append(keys);
  return entry;
}

// Pressing a button removes the keyboard (as the bot does) and the bot answers.
async function press(s, entry, action, play) {
  if (s !== state || entry.used || (!play && !s.interactive)) return;
  entry.used = true;
  const button = action === "solved" ? entry.solved : entry.ticket;
  button.classList.add("hd-press");
  await pause(play, 450);
  entry.keys.remove();
  let result;
  try {
    result =
      action === "solved"
        ? await py.call("solved", entry.reply.question_id)
        : await py.call("create_ticket", entry.reply.question_id);
  } catch (error) {
    fail(error);
    return;
  }
  if (s !== state) return;
  ui.chat.append(bubble("in", result.text));
  scrollDown();
  await renderQueue(s, result.ticket?.id, result.it_notification);
}

function setBusy(s, busy) {
  s.busy = busy;
  const off = busy || !s.interactive;
  ui.send.disabled = off;
  for (const button of ui.suggestions) button.disabled = off;
}

async function submit(text) {
  const s = state;
  const value = (text ?? ui.input.value).trim();
  if (!value || s.busy || !s.interactive) return;
  ui.input.value = "";
  setBusy(s, true);
  await sendMessage(value);
  if (s === state) setBusy(s, false);
}

// What the copilot did

const fixed = (value, digits = 2) => Number(value).toFixed(digits);

function meter(value, threshold) {
  const low = value < threshold;
  return el(
    "div",
    { class: `hd-meter${low ? " low" : ""}`, role: "img", "aria-label": `${fixed(value)} / ${fixed(threshold)}` },
    el("span", { style: { width: `${Math.min(100, Math.round(value * 100))}%` } }),
    el("i", { style: { left: `${Math.round(threshold * 100)}%` } }),
  );
}

function decisionRow(reply) {
  const parts = [];
  if (reply.answered) {
    const list = reply.sources.map((source) => `[${source.number}]`).join("");
    parts.push(el("span", { class: "d-badge ok", text: t("answeredWith", { list }) }));
  }
  if (reply.ticket) {
    parts.push(el("span", { class: PRIORITY_BADGE[reply.ticket.priority], text: reply.ticket.priority }));
    parts.push(el("span", { text: t("ticketMade", { id: reply.ticket.id }) }));
  }
  return el(
    "div",
    { class: "d-stack" },
    el("div", { class: "hd-decision" }, parts),
    reply.route ? el("p", { text: t(`route_${reply.route}`) }) : null,
    reply.ticket_reason ? el("p", { class: "hd-reason", text: reply.ticket_reason }) : null,
  );
}

function renderWork(reply) {
  const r = reply.retrieval;
  const top = r.hits[0];
  const matchedAny = new Set(r.hits.flatMap((hit) => hit.matched));
  const citedFiles = new Map(reply.sources.map((source) => [source.label, source.number]));

  const rows = r.hits.map((hit, i) =>
    el(
      "tr",
      {},
      el("td", { text: i + 1 }),
      el(
        "td",
        {},
        el("span", { class: "label", text: hit.label }),
        citedFiles.has(hit.label) ? [" ", el("span", { class: "d-badge ok", text: `[${citedFiles.get(hit.label)}] ${t("cited")}` })] : null,
        el("span", { class: "file", text: hit.file }),
        el("div", { class: "hd-terms" }, hit.matched.map((term) => el("span", { class: "hd-term hit", text: term }))),
      ),
      el("td", { class: "num", text: fixed(hit.score) }),
    ),
  );

  ui.work.replaceChildren(
    el("span", { class: "d-label", text: t("workTitle") }),
    el("p", { class: "hd-question", text: `“${reply.question}”` }),
    el("div", { class: "hd-block" }, el("span", { class: "d-label", text: t("decision") }), decisionRow(reply)),
    el(
      "div",
      { class: "hd-block" },
      el(
        "div",
        { class: "hd-decision" },
        el("span", { class: "d-label", text: t("confidence") }),
        el("span", { class: r.confident ? "d-badge ok" : "d-badge fail", text: r.confident ? t("covered") : t("notCovered") }),
      ),
      el(
        "div",
        {},
        el("div", { class: "hd-figure" }, el("span", { text: t("coverage", { value: r.coverage_label, min: fixed(info.min_coverage) }) })),
        meter(r.coverage, info.min_coverage),
        el("p", { class: "d-note", text: t("coverageHelp") }),
      ),
      el("div", { class: "hd-figure" }, el("span", { text: t("topScore", { value: top ? fixed(top.score) : "0.00", min: fixed(info.min_score, 1) }) })),
    ),
    el(
      "div",
      { class: "hd-block" },
      el("span", { class: "d-label", text: t("terms") }),
      el("div", { class: "hd-terms" }, r.terms.map((term) => el("span", { class: `hd-term${matchedAny.has(term) ? " hit" : ""}`, text: term }))),
    ),
    el(
      "div",
      { class: "hd-block" },
      el("span", { class: "d-label", text: t("topSources", { k: info.top_k }) }),
      r.hits.length
        ? el(
            "div",
            { class: "d-scroll" },
            el(
              "table",
              { class: "d-table hd-hits" },
              el("thead", {}, el("tr", {}, el("th", { text: "#" }), el("th", { text: t("section") }), el("th", { class: "num", text: t("score") }))),
              el("tbody", {}, rows),
            ),
          )
        : el("p", { class: "d-note", text: t("noHits") }),
    ),
  );
  ui.work.classList.remove("d-flash");
  void ui.work.offsetWidth; // restart the highlight
  ui.work.classList.add("d-flash");
}

// A /ticket message: no search, the rules triage the text directly.
function renderDirect(reply) {
  ui.work.replaceChildren(
    el("span", { class: "d-label", text: t("workTitle") }),
    el("p", { class: "hd-question", text: `“${reply.ticket.question}”` }),
    el("div", { class: "hd-block" }, el("span", { class: "d-label", text: t("decision") }), decisionRow({ ...reply, route: "DIRECT", answered: false, ticket_reason: reply.ticket.route_reason })),
  );
}

async function renderQueue(s, newId, notification) {
  let tickets, stats;
  try {
    [tickets, stats] = [await py.call("tickets"), await py.call("stats")];
  } catch (error) {
    fail(error);
    return;
  }
  if (s !== state) return;
  const items = tickets.map((ticket) =>
    el(
      "li",
      { class: ticket.id === newId ? "d-enter d-flash" : null },
      el("span", { class: PRIORITY_BADGE[ticket.priority], text: ticket.priority }),
      el(
        "div",
        {},
        el("span", { class: "summary", text: `#${ticket.id} ${ticket.summary}` }),
        el("span", { class: "sub", text: `${t(`cat_${ticket.category}`)} · ${t(`status_${ticket.status}`)} · ${ticket.reason}` }),
      ),
    ),
  );
  ui.queue.replaceChildren(...(items.length ? items : [el("li", { class: "d-note", text: t("queueEmpty") })]));
  ui.stats.textContent = t("statsLine", { q: stats.questions, a: stats.answered, s: stats.solved, o: stats.open_tickets });
  if (notification) {
    ui.itText.textContent = notification;
    ui.itBlock.hidden = false;
  }
}

// The page

function build() {
  const s = { keyboards: [], busy: false, interactive: false };
  const n = {};
  n.chat = el("div", { class: "d-chat", role: "log", "aria-live": "polite" });
  n.input = el("input", {
    class: "d-input",
    id: "hd-input",
    type: "text",
    autocomplete: "off",
    maxlength: "2000",
    placeholder: t("placeholder"),
    disabled: true,
  });
  n.send = el("button", { class: "d-btn solid", type: "submit", text: t("send"), disabled: true });
  const phone = el(
    "section",
    { class: "d-phone hd-phone", "aria-label": t("chatTitle") },
    el(
      "div",
      { class: "d-phone-head" },
      el("div", { class: "d-avatar", text: "IT" }),
      el(
        "div",
        { class: "hd-head-text" },
        el("div", { class: "name", text: t("botName", { company: info.company }) }),
        el("div", { class: "sub", text: t("botSub", { name: info.employee }) }),
      ),
      el("span", { class: "d-badge sim", text: t("demoMode") }),
    ),
    n.chat,
    el(
      "form",
      {
        class: "d-composer",
        onsubmit: (event) => {
          event.preventDefault();
          submit();
        },
      },
      el("label", { class: "hd-sr", for: "hd-input", text: t("messageLabel") }),
      n.input,
      n.send,
    ),
  );
  n.suggestions = info.suggestions.map((text) =>
    el("button", { class: "d-btn", type: "button", text, disabled: true, onclick: () => submit(text) }),
  );

  n.work = el("section", { class: "d-panel", "aria-live": "polite" }, el("span", { class: "d-label", text: t("workTitle") }), el("p", { class: "d-note", text: t("workEmpty") }));
  n.queue = el("ol", { class: "hd-queue" }, el("li", { class: "d-note", text: t("queueEmpty") }));
  n.stats = el("p", { class: "d-note" });
  n.itText = el("pre", { class: "hd-it" });
  n.itBlock = el("div", { class: "d-stack", hidden: true }, el("span", { class: "d-label", text: t("itChat") }), n.itText);

  demo.stage.replaceChildren(
    el("p", { class: "d-note", text: t("intro") }),
    el(
      "div",
      { class: "d-cols" },
      el(
        "div",
        { class: "d-stack hd-col" },
        el("span", { class: "d-label", text: t("chatTitle") }),
        phone,
        el("div", { class: "d-stack hd-suggest" }, el("span", { class: "d-label", text: t("suggestTitle") }), el("div", { class: "d-keys" }, n.suggestions)),
      ),
      el(
        "div",
        { class: "d-stack hd-col" },
        n.work,
        el("section", { class: "d-panel d-stack" }, el("span", { class: "d-label", text: t("queueTitle") }), n.queue, n.stats, n.itBlock),
      ),
    ),
    el(
      "div",
      { class: "d-panel d-stack" },
      el("span", { class: "d-label", text: t("howTitle") }),
      el("p", { class: "d-note", text: t("how", { docs: info.documents, sections: info.sections }) }),
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
    await renderQueue(state);
  },
  async script(play) {
    const s = state;
    await sendMessage("/start", play);
    await play.wait(1800);
    for (const item of info.script) {
      await play.type(ui.input, item.question);
      await play.wait(250);
      ui.input.value = "";
      const reply = await sendMessage(item.question, play);
      await play.wait(reply?.ticket ? 2600 : 2000);
      if (item.then && reply?.buttons) {
        const entry = s.keyboards.at(-1);
        await press(s, entry, item.then === "solved" ? "solved" : "ticket", play);
        await play.wait(1200);
      }
    }
    play.show(ui.work);
    await play.wait(1500);
  },
  interactive() {
    const s = state;
    s.interactive = true;
    ui.input.disabled = false;
    for (const entry of s.keyboards) {
      entry.solved.disabled = false;
      entry.ticket.disabled = false;
    }
    setBusy(s, false);
  },
});
