// Copies each project's real Python source into the website for its in-browser demo:
//   ../projects/<name>/web_demo.json  ->  public/demos/<slug>/py/**  +  public/demos/<slug>/manifest.json
//
// web_demo.json:
//   { "slug": "pii-guard", "entry": "app.web_demo", "packages": ["pyyaml"], "micropip": ["phonenumbers"],
//     "files": ["app/__init__.py", "app/detectors/*.py", "policy.yaml"] }
// A "*" matches file names inside one folder; there is no recursive "**".
//
// The copies are committed: the Railway build only sees site/, not projects/.
// Usage: npm run demos                  (copy all)
//        npm run demos -- --only <slug>  (copy one)
//        npm run demos -- --check       (exit 1 if a copy is out of date; used in CI)

import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const projectsDir = path.resolve(root, "..", "projects");
const demosDir = path.join(root, "public", "demos");
const check = process.argv.includes("--check");
const only = process.argv.includes("--only") ? process.argv[process.argv.indexOf("--only") + 1] : null;

function expand(projectDir, pattern) {
  if (!pattern.includes("*")) {
    if (!fs.existsSync(path.join(projectDir, pattern))) throw new Error(`Missing file: ${pattern}`);
    return [pattern];
  }
  const dir = path.posix.dirname(pattern);
  const name = new RegExp(`^${path.posix.basename(pattern).replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`);
  return fs
    .readdirSync(path.join(projectDir, dir), { withFileTypes: true })
    .filter((entry) => entry.isFile() && name.test(entry.name))
    .map((entry) => path.posix.join(dir, entry.name))
    .sort();
}

function plan() {
  const demos = [];
  for (const project of fs.readdirSync(projectsDir).sort()) {
    const configFile = path.join(projectsDir, project, "web_demo.json");
    if (!fs.existsSync(configFile)) continue;
    const config = JSON.parse(fs.readFileSync(configFile, "utf8"));
    const projectDir = path.join(projectsDir, project);
    const files = [...new Set(config.files.flatMap((pattern) => expand(projectDir, pattern)))];
    const manifest = {
      project,
      entry: config.entry,
      packages: config.packages ?? [],
      micropip: config.micropip ?? [],
      files,
    };
    if (!only || config.slug === only) demos.push({ slug: config.slug, projectDir, manifest });
  }
  return demos;
}

function listFiles(dir, base = dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? listFiles(full, base) : [path.relative(base, full).split(path.sep).join("/")];
  });
}

const problems = [];
for (const { slug, projectDir, manifest } of plan()) {
  const outDir = path.join(demosDir, slug);
  const pyDir = path.join(outDir, "py");
  const manifestFile = path.join(outDir, "manifest.json");
  const manifestText = `${JSON.stringify(manifest, null, 2)}\n`;

  if (check) {
    if (!fs.existsSync(manifestFile) || fs.readFileSync(manifestFile, "utf8") !== manifestText) {
      problems.push(`${slug}: manifest.json is out of date`);
    }
    const present = new Set(listFiles(pyDir));
    for (const file of manifest.files) {
      const copy = path.join(pyDir, file);
      if (!present.delete(file) || !fs.readFileSync(copy).equals(fs.readFileSync(path.join(projectDir, file)))) {
        problems.push(`${slug}: py/${file} differs from projects/${manifest.project}/${file}`);
      }
    }
    for (const extra of present) problems.push(`${slug}: py/${extra} is not in web_demo.json`);
    continue;
  }

  fs.rmSync(pyDir, { recursive: true, force: true });
  for (const file of manifest.files) {
    const target = path.join(pyDir, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(projectDir, file), target);
  }
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(manifestFile, manifestText);
  console.log(`demo ${slug}: ${manifest.files.length} files from projects/${manifest.project}`);
}

if (check) {
  if (problems.length) {
    console.error(`Demo copies are out of date (run npm run demos):\n- ${problems.join("\n- ")}`);
    process.exit(1);
  }
  console.log("Demo copies match the projects.");
}
