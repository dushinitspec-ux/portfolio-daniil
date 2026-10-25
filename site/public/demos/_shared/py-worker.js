// Runs Python (Pyodide) in a Web Worker, so the page stays smooth while Python starts and
// works. One worker per demo. Messages:
//   in:  { type: "init", base, manifest }       -> out: { type: "progress", step } ... { type: "ready" }
//   in:  { type: "call", id, name, args }        -> out: { type: "result", id, ok, value | error }
// Every value crosses the boundary as JSON, so a demo never deals with Python proxies.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.5/full/";
importScripts(`${PYODIDE}pyodide.js`);

const ROOT = "/home/pyodide/demo";
let pyodide = null;
let call = null;

const send = (message) => self.postMessage(message);

async function init({ base, manifest }) {
  send({ type: "progress", step: "runtime" });
  pyodide = await loadPyodide({ indexURL: PYODIDE });

  const packages = manifest.packages ?? [];
  const wheels = manifest.micropip ?? [];
  if (packages.length || wheels.length) {
    send({ type: "progress", step: "packages" });
    if (packages.length) await pyodide.loadPackage(packages);
    if (wheels.length) {
      await pyodide.loadPackage("micropip");
      await pyodide.pyimport("micropip").install(wheels);
    }
  }

  // The project's own source files, copied unchanged from projects/<name>/ by
  // scripts/build-demos.mjs, are written into the in-browser file system.
  send({ type: "progress", step: "code" });
  await Promise.all(
    manifest.files.map(async (file) => {
      const response = await fetch(`${base}py/${file}`);
      if (!response.ok) throw new Error(`Could not load ${file} (${response.status})`);
      const target = `${ROOT}/${file}`;
      pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
      pyodide.FS.writeFile(target, new Uint8Array(await response.arrayBuffer()));
    }),
  );

  pyodide.globals.set("ENTRY_MODULE", manifest.entry);
  await pyodide.runPythonAsync(`
import importlib, inspect, json, os, sys
sys.path.insert(0, "${ROOT}")
os.chdir("${ROOT}")
entry = importlib.import_module(ENTRY_MODULE)

async def demo_call(name, args_json):
    result = getattr(entry, name)(*json.loads(args_json))
    if inspect.isawaitable(result):
        result = await result
    return json.dumps(result, default=str, ensure_ascii=False)
`);
  call = pyodide.globals.get("demo_call");
  send({ type: "ready" });
}

self.onmessage = async (event) => {
  const message = event.data;
  if (message.type === "init") {
    try {
      await init(message);
    } catch (error) {
      send({ type: "failed", error: String(error?.message ?? error) });
    }
    return;
  }
  if (message.type === "call") {
    try {
      const json = await call(message.name, JSON.stringify(message.args ?? []));
      send({ type: "result", id: message.id, ok: true, value: JSON.parse(json) });
    } catch (error) {
      send({ type: "result", id: message.id, ok: false, error: String(error?.message ?? error) });
    }
  }
};
