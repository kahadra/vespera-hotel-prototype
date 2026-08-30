"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const ELECTRON_DIST = path.join(PROJECT_ROOT, "node_modules", "electron", "dist");
const OUTPUT_ROOT = path.join(PROJECT_ROOT, "out");
const OUTPUT_DIRECTORY = path.join(OUTPUT_ROOT, "Vespera Hotel-win32-x64");
const APP_DIRECTORY = path.join(OUTPUT_DIRECTORY, "resources", "app");

function assertInside(parent, candidate) {
  const root = path.resolve(parent);
  const target = path.resolve(candidate);
  if (target === root || !target.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Unsafe package target: ${target}`);
  }
  return target;
}

function copyFile(relativePath) {
  const source = path.join(PROJECT_ROOT, relativePath);
  const destination = path.join(APP_DIRECTORY, relativePath);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  fs.copyFileSync(source, destination);
}

function copyDirectory(relativePath) {
  const source = path.join(PROJECT_ROOT, relativePath);
  const destination = path.join(APP_DIRECTORY, relativePath);
  fs.cpSync(source, destination, { recursive: true, force: true });
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

if (process.platform !== "win32" || process.arch !== "x64") {
  throw new Error(`This spike packager currently supports win32-x64, not ${process.platform}-${process.arch}`);
}
if (!fs.existsSync(path.join(ELECTRON_DIST, "electron.exe"))) {
  throw new Error("Electron runtime is missing. Run npm install before packaging.");
}

const safeOutput = assertInside(OUTPUT_ROOT, OUTPUT_DIRECTORY);
if (fs.existsSync(safeOutput)) fs.rmSync(safeOutput, { recursive: true, force: true });
fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
fs.cpSync(ELECTRON_DIST, safeOutput, { recursive: true, force: true });

const defaultApp = path.join(safeOutput, "resources", "default_app.asar");
if (fs.existsSync(defaultApp)) fs.rmSync(defaultApp, { force: true });
fs.mkdirSync(APP_DIRECTORY, { recursive: true });

for (const relativePath of [
  "index.html",
  "styles.css",
  "desktop/main.cjs",
  "desktop/preload.cjs",
  "desktop/file-storage.cjs",
]) copyFile(relativePath);
for (const relativePath of ["src", "data"]) copyDirectory(relativePath);

const rootPackage = JSON.parse(fs.readFileSync(path.join(PROJECT_ROOT, "package.json"), "utf8"));
const packagedPackage = {
  name: rootPackage.name,
  productName: rootPackage.productName,
  version: rootPackage.version,
  private: true,
  main: rootPackage.main,
};
fs.writeFileSync(
  path.join(APP_DIRECTORY, "package.json"),
  `${JSON.stringify(packagedPackage, null, 2)}\n`,
  "utf8",
);

const electronExecutable = path.join(safeOutput, "electron.exe");
const gameExecutable = path.join(safeOutput, "VesperaHotel.exe");
fs.renameSync(electronExecutable, gameExecutable);

const manifest = {
  artifact_type: "ELECTRON_DESKTOP_SPIKE",
  production_release: false,
  platform: process.platform,
  arch: process.arch,
  app_version: rootPackage.version,
  electron_version: require("electron/package.json").version,
  executable: path.basename(gameExecutable),
  executable_sha256: sha256(gameExecutable),
  runtime_authority: ["index.html", "styles.css", "src", "data", "desktop"],
};
fs.writeFileSync(
  path.join(safeOutput, "desktop-spike-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify({
  status: "PACKAGED",
  output: safeOutput,
  executable: gameExecutable,
  sha256: manifest.executable_sha256,
}));
