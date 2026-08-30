"use strict";

const path = require("node:path");
const { pathToFileURL } = require("node:url");
const {
  app,
  BrowserWindow,
  ipcMain,
  net,
  protocol,
  session,
} = require("electron");
const { FileStorageService } = require("./file-storage.cjs");

const APP_SCHEME = "vespera";
const APP_HOST = "app";
const APP_ORIGIN_PREFIX = `${APP_SCHEME}://${APP_HOST}/`;
const IPC_BOOTSTRAP = "vespera:storage:bootstrap";
const IPC_MUTATE = "vespera:storage:mutate";
const IPC_STATUS = "vespera:storage:status";
const IS_TEST = process.argv.includes("--vespera-test");
const DEFAULT_WINDOW_SIZE = Object.freeze({ width: 1280, height: 720 });
const MIN_WINDOW_SIZE = Object.freeze({ width: 960, height: 600 });
const MAX_TEST_WINDOW_DIMENSION = 8192;
const TEST_WINDOW_SIZE_OPTION = "--vespera-test-window-size";

function requestedWindowSize(argv, isTest) {
  const sizeArguments = argv.filter((argument) => (
    argument.startsWith(TEST_WINDOW_SIZE_OPTION)
  ));
  if (!isTest && sizeArguments.length > 0) {
    throw new Error(`${TEST_WINDOW_SIZE_OPTION} is only allowed with --vespera-test`);
  }
  if (sizeArguments.length === 0) return DEFAULT_WINDOW_SIZE;
  if (sizeArguments.length !== 1) {
    throw new Error(`${TEST_WINDOW_SIZE_OPTION} may be specified only once`);
  }

  const match = /^--vespera-test-window-size=([1-9]\d*)x([1-9]\d*)$/.exec(
    sizeArguments[0],
  );
  if (!match) {
    throw new Error(
      `${TEST_WINDOW_SIZE_OPTION} must use <integer>x<integer> format`,
    );
  }
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isSafeInteger(width) || !Number.isSafeInteger(height)) {
    throw new Error(`${TEST_WINDOW_SIZE_OPTION} dimensions must be safe integers`);
  }
  if (
    width < MIN_WINDOW_SIZE.width
    || height < MIN_WINDOW_SIZE.height
    || width > MAX_TEST_WINDOW_DIMENSION
    || height > MAX_TEST_WINDOW_DIMENSION
  ) {
    throw new Error(
      `${TEST_WINDOW_SIZE_OPTION} must be at least `
      + `${MIN_WINDOW_SIZE.width}x${MIN_WINDOW_SIZE.height} and no dimension may exceed `
      + MAX_TEST_WINDOW_DIMENSION,
    );
  }
  return Object.freeze({ width, height });
}

const MAIN_WINDOW_SIZE = requestedWindowSize(process.argv, IS_TEST);

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
      codeCache: true,
    },
  },
]);
app.enableSandbox();

const testUserDataArgument = process.argv.find((argument) => (
  argument.startsWith("--vespera-user-data-dir=")
));
if (IS_TEST && testUserDataArgument) {
  const requestedPath = testUserDataArgument.slice("--vespera-user-data-dir=".length);
  if (!path.isAbsolute(requestedPath)) {
    throw new Error("Electron test userData path must be absolute");
  }
  app.setPath("userData", path.resolve(requestedPath));
}

let mainWindow = null;
let storageService = null;

function response(status, body) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

function allowedRuntimeAsset(relativePath) {
  return relativePath === "index.html"
    || relativePath === "styles.css"
    || /^src\/[a-z0-9-]+\.js$/i.test(relativePath)
    || relativePath === "data/prototype_v1.json";
}

function runtimeAssetPath(requestUrl, appRoot) {
  let parsed;
  try {
    parsed = new URL(requestUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== `${APP_SCHEME}:` || parsed.hostname !== APP_HOST) return null;
  let decoded;
  try {
    decoded = decodeURIComponent(parsed.pathname);
  } catch {
    return null;
  }
  if (decoded.includes("\0") || decoded.includes("\\")) return null;
  const pieces = decoded.split("/").filter(Boolean);
  if (pieces.some((piece) => piece === "." || piece === "..")) return null;
  const relativePath = pieces.join("/") || "index.html";
  if (!allowedRuntimeAsset(relativePath)) return null;
  const root = path.resolve(appRoot);
  const resolved = path.resolve(root, ...relativePath.split("/"));
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) return null;
  return resolved;
}

function trustedStorageSender(event) {
  const frame = event.senderFrame;
  return Boolean(
    frame
    && frame === event.sender.mainFrame
    && typeof frame.url === "string"
    && frame.url.startsWith(APP_ORIGIN_PREFIX),
  );
}

function replyFailure(event, error, fallbackCode) {
  event.returnValue = {
    ok: false,
    code: error?.code ?? fallbackCode,
    message: error?.message ?? "데스크톱 저장 요청에 실패했습니다.",
  };
}

function installStorageIpc() {
  ipcMain.on(IPC_BOOTSTRAP, (event) => {
    if (!trustedStorageSender(event)) {
      replyFailure(event, null, "UNTRUSTED_SENDER");
      return;
    }
    try {
      const bootstrap = storageService.bootstrap();
      event.returnValue = {
        ok: true,
        entries: bootstrap.entries,
        diagnostics: storageService.diagnostics(),
      };
    } catch (error) {
      replyFailure(event, error, "BOOTSTRAP_FAILED");
    }
  });

  ipcMain.on(IPC_MUTATE, (event, request) => {
    if (!trustedStorageSender(event)) {
      replyFailure(event, null, "UNTRUSTED_SENDER");
      return;
    }
    try {
      if (!request || typeof request !== "object" || Array.isArray(request)) {
        throw Object.assign(new Error("잘못된 저장 요청입니다."), { code: "INVALID_REQUEST" });
      }
      const expectedKeys = request.op === "set" ? ["key", "op", "value"] : ["key", "op"];
      const actualKeys = Object.keys(request).sort();
      if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
        throw Object.assign(new Error("저장 요청 필드가 허용 목록과 다릅니다."), { code: "INVALID_REQUEST_FIELDS" });
      }
      let revision;
      if (request.op === "set") revision = storageService.setItem(request.key, request.value);
      else if (request.op === "remove") revision = storageService.removeItem(request.key);
      else throw Object.assign(new Error("지원하지 않는 저장 작업입니다."), { code: "INVALID_OPERATION" });
      event.returnValue = { ok: true, revision };
    } catch (error) {
      replyFailure(event, error, "MUTATION_FAILED");
    }
  });

  ipcMain.on(IPC_STATUS, (event) => {
    if (!trustedStorageSender(event)) {
      replyFailure(event, null, "UNTRUSTED_SENDER");
      return;
    }
    event.returnValue = { ok: true, diagnostics: storageService.diagnostics() };
  });
}

function secureWindow(window) {
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => {
    if (!event.url.startsWith(APP_ORIGIN_PREFIX)) event.preventDefault();
  });
  window.webContents.on("did-fail-load", (_event, code, description, url, isMainFrame) => {
    if (isMainFrame) console.error("Electron main-frame load failed", { code, description, url });
  });
  window.webContents.on("render-process-gone", (_event, details) => {
    console.error("Electron renderer process exited", details);
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: MAIN_WINDOW_SIZE.width,
    height: MAIN_WINDOW_SIZE.height,
    minWidth: MIN_WINDOW_SIZE.width,
    minHeight: MIN_WINDOW_SIZE.height,
    show: !IS_TEST,
    backgroundColor: "#11100f",
    title: "베스페라 호텔",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      devTools: !app.isPackaged || IS_TEST,
    },
  });
  secureWindow(window);
  window.once("ready-to-show", () => {
    if (!IS_TEST) window.show();
  });
  window.loadURL(`${APP_ORIGIN_PREFIX}index.html`);
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
  });
  return window;
}

// Parallel/restart tests use isolated userData roots and must not redirect into
// a just-closed test instance. Production keeps the normal single-instance lock.
const hasSingleInstanceLock = IS_TEST || app.requestSingleInstanceLock();
app.on("child-process-gone", (_event, details) => {
  console.error("Electron child process exited", details);
});
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    const appRoot = app.getAppPath();
    protocol.handle(APP_SCHEME, (request) => {
      const assetPath = runtimeAssetPath(request.url, appRoot);
      return assetPath
        ? net.fetch(pathToFileURL(assetPath).toString())
        : response(404, "Not Found");
    });
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
      callback(false);
    });
    session.defaultSession.setPermissionCheckHandler(() => false);
    storageService = new FileStorageService(path.join(
      app.getPath("userData"),
      "save-data",
      "v1",
      "profiles",
      "local",
    ));
    storageService.bootstrap();
    installStorageIpc();
    mainWindow = createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow();
    });
  }).catch((error) => {
    console.error("Electron startup failed", error);
    app.exit(1);
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
}

module.exports = {
  allowedRuntimeAsset,
  runtimeAssetPath,
};
