"use strict";

const path = require("node:path");
const { spawnSync } = require("node:child_process");

const environment = { ...process.env };
delete environment.ELECTRON_RUN_AS_NODE;
delete environment.Electron_Run_As_Node;
delete environment.CHROME_CRASHPAD_PIPE_NAME;
delete environment.CHROME_CRASHPAD_SERVER_URL;

const electronExecutable = require("electron");
const projectRoot = path.resolve(__dirname, "..");
const forwarded = process.argv.slice(2);
const electronSwitches = forwarded.filter((argument) => !argument.startsWith("--vespera-"));
const appArguments = forwarded.filter((argument) => argument.startsWith("--vespera-"));
const result = spawnSync(
  electronExecutable,
  [...electronSwitches, projectRoot, ...appArguments],
  { cwd: projectRoot, env: environment, stdio: "inherit" },
);
if (result.error) throw result.error;
process.exit(result.status ?? 1);
