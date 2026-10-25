// Shared runtime of the in-browser demos (no build step, plain ES modules).
//
//   const demo = createDemo({ title, strings });   // language, theme, shell (status bar + stage)
//   const py = await demo.python();                 // starts Python with the project's real code
//   demo.autoplay({ reset, script, interactive });  // plays a scripted run, then hands over
//
// The page is meant to live in an iframe on the portfolio site (?lang=ru&theme=dark), but it
// also works when opened directly.

const LANGS = ["en", "ru", "tr", "de"];

const COMMON = {
  en: {
    loading: "Starting Python in your browser",
    stepRuntime: "Python 3.13 (Pyodide, WebAssembly)",
    stepPackages: "Libraries the project uses",
    stepCode: "This project's source code",
    privacy: "Everything runs on your device. Nothing is sent to a server.",
    statusLoading: "Loading",
    statusAuto: "Autoplay",
    statusReady: "Your turn — try it",
    statusError: "Could not start",
    skip: "Skip",
    replay: "Replay",
    retry: "Try again",
    error: "Python could not be loaded. Check the connection and try again.",
    simulated: "Simulated data",
    sample: "Sample data",
  },
  ru: {
    loading: "Запускаю Python в вашем браузере",
    stepRuntime: "Python 3.13 (Pyodide, WebAssembly)",
    stepPackages: "Библиотеки проекта",
    stepCode: "Исходный код этого проекта",
    privacy: "Всё работает на вашем устройстве. На сервер ничего не отправляется.",
    statusLoading: "Загрузка",
    statusAuto: "Автопоказ",
    statusReady: "Ваша очередь — попробуйте",
    statusError: "Не удалось запустить",
    skip: "Пропустить",
    replay: "Повторить",
    retry: "Ещё раз",
    error: "Не удалось загрузить Python. Проверьте интернет и попробуйте ещё раз.",
    simulated: "Симуляция",
    sample: "Пример данных",
  },
  tr: {
    loading: "Python tarayıcınızda başlatılıyor",
    stepRuntime: "Python 3.13 (Pyodide, WebAssembly)",
    stepPackages: "Projenin kütüphaneleri",
    stepCode: "Bu projenin kaynak kodu",
    privacy: "Her şey cihazınızda çalışır. Sunucuya hiçbir şey gönderilmez.",
    statusLoading: "Yükleniyor",
    statusAuto: "Otomatik gösterim",
    statusReady: "Sıra sizde — deneyin",
    statusError: "Başlatılamadı",
    skip: "Geç",
    replay: "Tekrar oynat",
    retry: "Tekrar dene",
    error: "Python yüklenemedi. Bağlantınızı kontrol edip tekrar deneyin.",
    simulated: "Simülasyon",
    sample: "Örnek veri",
  },
  de: {
    loading: "Python startet in Ihrem Browser",
    stepRuntime: "Python 3.13 (Pyodide, WebAssembly)",
    stepPackages: "Bibliotheken des Projekts",
    stepCode: "Quellcode dieses Projekts",
    privacy: "Alles läuft auf Ihrem Gerät. Nichts wird an einen Server gesendet.",
    statusLoading: "Lädt",
    statusAuto: "Automatische Vorführung",
    statusReady: "Jetzt Sie — probieren Sie es aus",
    statusError: "Start fehlgeschlagen",
    skip: "Überspringen",
    replay: "Nochmal",
    retry: "Erneut versuchen",
    error: "Python konnte nicht geladen werden. Bitte Verbindung prüfen und erneut versuchen.",
    simulated: "Simulierte Daten",
    sample: "Beispieldaten",
  },
};

const params = new URLSearchParams(location.search);
export const lang = LANGS.includes(params.get("lang")) ? params.get("lang") : "en";
export const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Builds an element. Text children are set as text, never as HTML, so user input stays inert. */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** Interpolates {name} placeholders. */
export function format(template, vars = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) => (key in vars ? String(vars[key]) : `{${key}}`));
}

function applyTheme(theme) {
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

// The parent page sizes the iframe to the content, so the site scrolls instead of the frame.
function reportHeight() {
  if (window.parent === window) return;
  const send = () =>
    window.parent.postMessage({ type: "demo:height", height: document.documentElement.scrollHeight }, "*");
  new ResizeObserver(send).observe(document.documentElement);
  send();
}

const CANCELLED = Symbol("cancelled");

/** Plays a scripted run: waits and typing can be skipped (finish instantly) or replayed. */
class Player {
  constructor() {
    this.fast = false;
    this.run = 0;
    this.pending = new Set();
  }
  get cancelled() {
    return this.current !== this.run;
  }
  check() {
    if (this.cancelled) throw CANCELLED;
  }
  /** Pauses the script; instant after Skip, shorter with reduced motion. */
  wait(ms) {
    this.check();
    if (this.fast) return Promise.resolve();
    const duration = reducedMotion ? Math.min(ms, 250) : ms;
    return new Promise((resolve, reject) => {
      const entry = { resolve, reject };
      entry.timer = setTimeout(() => {
        this.pending.delete(entry);
        this.cancelled ? reject(CANCELLED) : resolve();
      }, duration);
      this.pending.add(entry);
    });
  }
  /** Types text into an input or textarea like a person would. */
  async type(input, text, { cps = 32 } = {}) {
    this.check();
    input.focus({ preventScroll: true });
    if (this.fast || reducedMotion) {
      input.value = text;
    } else {
      input.value = "";
      for (const char of text) {
        if (this.fast) {
          input.value = text;
          break;
        }
        input.value += char;
        await this.wait(1000 / cps);
      }
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  /** Brings an element into view inside the demo. */
  show(node) {
    if (!this.fast) node.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }
  skip() {
    this.fast = true;
    for (const entry of this.pending) {
      clearTimeout(entry.timer);
      entry.resolve();
    }
    this.pending.clear();
  }
  cancel() {
    this.run += 1;
    for (const entry of this.pending) {
      clearTimeout(entry.timer);
      entry.reject(CANCELLED);
    }
    this.pending.clear();
  }
}

export function createDemo({ title = "", strings = {} } = {}) {
  const t = (key, vars) => {
    const own = strings[lang]?.[key] ?? strings.en?.[key];
    const text = own ?? COMMON[lang][key] ?? COMMON.en[key] ?? key;
    return vars ? format(text, vars) : text;
  };

  document.documentElement.lang = lang;
  if (title) document.title = title;
  applyTheme(params.get("theme"));
  window.addEventListener("message", (event) => {
    if (event.source === window.parent && event.data?.type === "theme") applyTheme(event.data.theme);
  });

  const statusText = el("span", { text: t("statusLoading") });
  const status = el("div", { class: "d-status", dataset: { state: "loading" }, role: "status" }, el("span", { class: "d-dot" }), statusText);
  const skipButton = el("button", { class: "d-btn", type: "button", hidden: true, text: t("skip") });
  const replayButton = el("button", { class: "d-btn", type: "button", hidden: true, text: t("replay") });
  const bar = el("div", { class: "d-bar" }, status, el("div", { class: "d-row" }, skipButton, replayButton));
  const stage = el("div", { class: "d-stage" });
  const root = el("div", { class: "d-root" }, bar, stage);
  document.getElementById("demo").replaceChildren(root);
  reportHeight();

  const setStatus = (state) => {
    status.dataset.state = state;
    statusText.textContent = t(
      { loading: "statusLoading", auto: "statusAuto", ready: "statusReady", error: "statusError" }[state],
    );
    skipButton.hidden = state !== "auto";
    replayButton.hidden = state !== "ready";
  };

  const player = new Player();
  skipButton.addEventListener("click", () => player.skip());

  /** Starts Python with the files listed in ./manifest.json and returns { call }. */
  async function python() {
    const steps = { runtime: "stepRuntime", packages: "stepPackages", code: "stepCode" };
    const items = Object.fromEntries(Object.entries(steps).map(([key, label]) => [key, el("li", { text: t(label) })]));
    const loader = el(
      "div",
      { class: "d-loader" },
      el("p", { class: "d-title", text: t("loading") }),
      el("div", { class: "d-progress" }, el("span")),
      el("ul", { class: "d-steps" }, Object.values(items)),
      el("p", { class: "d-note", text: t("privacy") }),
    );
    stage.replaceChildren(loader);
    setStatus("loading");

    const base = new URL(".", location.href).href;
    const manifest = await (await fetch(`${base}manifest.json`)).json();
    const worker = new Worker(new URL("./py-worker.js", import.meta.url));
    const waiting = new Map();
    let nextId = 0;

    await new Promise((resolve, reject) => {
      worker.onmessage = ({ data }) => {
        if (data.type === "progress") {
          let reached = false;
          for (const [key, item] of Object.entries(items)) {
            if (key === data.step) {
              item.dataset.state = "active";
              reached = true;
            } else if (!reached) item.dataset.state = "done";
          }
        } else if (data.type === "ready") {
          for (const item of Object.values(items)) item.dataset.state = "done";
          resolve();
        } else if (data.type === "failed") reject(new Error(data.error));
        else if (data.type === "result") {
          const job = waiting.get(data.id);
          waiting.delete(data.id);
          data.ok ? job.resolve(data.value) : job.reject(new Error(data.error));
        }
      };
      worker.onerror = (event) => reject(new Error(event.message || "Worker failed"));
      worker.postMessage({ type: "init", base, manifest });
    }).catch((error) => {
      setStatus("error");
      console.error(error);
      stage.replaceChildren(
        el(
          "div",
          { class: "d-loader" },
          el("p", { class: "d-title", text: t("error") }),
          el("p", { class: "d-note mono", text: String(error.message).slice(0, 300) }),
          el("div", {}, el("button", { class: "d-btn solid", type: "button", text: t("retry"), onclick: () => location.reload() })),
        ),
      );
      throw error;
    });

    stage.replaceChildren();
    return {
      /** Calls a function of the demo's Python entry module; arguments and result are JSON. */
      call(name, ...args) {
        const id = nextId++;
        // A Python call cannot be cancelled. If Replay restarts the autoplay while a call made
        // by the old run is in flight, its result is dropped, so the old script never writes
        // into the new run's UI.
        const fromAutoplay = status.dataset.state === "auto";
        const run = player.current;
        const stale = () => fromAutoplay && player.current !== run;
        return new Promise((resolve, reject) => {
          waiting.set(id, {
            resolve: (value) => stale() || resolve(value),
            reject: (error) => stale() || reject(error),
          });
          worker.postMessage({ type: "call", id, name, args });
        });
      },
    };
  }

  /**
   * reset()           — clears the stage and builds the demo's UI (controls disabled)
   * script(player)    — the scripted run: player.wait(ms), player.type(input, text), player.show(node)
   * interactive()     — enables the controls so the visitor can try their own input
   */
  function autoplay({ reset, script, interactive }) {
    const start = async () => {
      player.cancel();
      player.current = player.run;
      player.fast = false;
      await reset();
      setStatus("auto");
      try {
        await script(player);
      } catch (error) {
        if (error === CANCELLED) return;
        console.error(error);
      }
      if (player.cancelled) return;
      setStatus("ready");
      await interactive?.();
    };
    replayButton.onclick = start;
    return start();
  }

  return { t, el, stage, setStatus, python, autoplay, player, lang };
}
