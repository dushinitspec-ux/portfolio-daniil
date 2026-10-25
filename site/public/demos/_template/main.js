// Reference demo for the shared runtime: load Python, play a scripted run, then let the
// visitor try. Real demos keep this shape: reset() builds the UI, script() drives it,
// interactive() unlocks the controls.
import { createDemo, el } from "../_shared/demo.js";
import strings from "./strings.js";

const demo = createDemo({ title: "Demo template", strings });
const { t } = demo;
const py = await demo.python();

let input, button, result;

async function render(text) {
  const value = await py.call("analyse", text);
  result.replaceChildren(
    el("table", { class: "d-table d-enter" },
      el("tbody", {},
        el("tr", {}, el("th", { text: t("words") }), el("td", { class: "num", text: value.words })),
        el("tr", {}, el("th", { text: t("upper") }), el("td", { text: value.upper })),
      ),
    ),
  );
}

demo.autoplay({
  reset() {
    input = el("textarea", { class: "d-textarea", disabled: true });
    button = el("button", { class: "d-btn solid", type: "button", disabled: true, text: t("run") });
    result = el("div");
    button.onclick = () => render(input.value);
    demo.stage.replaceChildren(
      el("div", { class: "d-cols" },
        el("div", { class: "d-panel d-stack" }, el("label", { class: "d-label", text: t("input") }), input, el("div", {}, button)),
        el("div", { class: "d-panel" }, el("span", { class: "d-label", text: "Python" }), result),
      ),
    );
  },
  async script(play) {
    await play.wait(400);
    await play.type(input, "Hello from Python running in the browser");
    await play.wait(300);
    await render(input.value);
    await play.wait(800);
  },
  interactive() {
    input.disabled = false;
    button.disabled = false;
  },
});
