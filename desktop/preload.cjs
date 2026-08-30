"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const IPC_BOOTSTRAP = "vespera:storage:bootstrap";
const IPC_MUTATE = "vespera:storage:mutate";
const IPC_STATUS = "vespera:storage:status";

function bridgeError(result, fallback) {
  const error = new Error(result?.message ?? fallback);
  error.code = result?.code ?? "DESKTOP_STORAGE_ERROR";
  return error;
}

try {
  const bootstrap = ipcRenderer.sendSync(IPC_BOOTSTRAP);
  if (!bootstrap?.ok || !Array.isArray(bootstrap.entries)) {
    throw bridgeError(bootstrap, "데스크톱 저장소를 불러오지 못했습니다.");
  }
  const cache = new Map(bootstrap.entries);
  const storage = Object.freeze({
    getItem(key) {
      const normalizedKey = String(key);
      return cache.has(normalizedKey) ? cache.get(normalizedKey) : null;
    },
    setItem(key, value) {
      const normalizedKey = String(key);
      const normalizedValue = String(value);
      const result = ipcRenderer.sendSync(IPC_MUTATE, {
        op: "set",
        key: normalizedKey,
        value: normalizedValue,
      });
      if (!result?.ok) throw bridgeError(result, "저장 파일을 기록하지 못했습니다.");
      cache.set(normalizedKey, normalizedValue);
    },
    removeItem(key) {
      const normalizedKey = String(key);
      const result = ipcRenderer.sendSync(IPC_MUTATE, {
        op: "remove",
        key: normalizedKey,
      });
      if (!result?.ok) throw bridgeError(result, "저장 파일을 삭제하지 못했습니다.");
      cache.delete(normalizedKey);
    },
  });
  contextBridge.exposeInMainWorld("vesperaDesktop", Object.freeze({
    platform: "electron",
    storageReady: true,
    storageError: null,
    storage,
    storageStatus() {
      const result = ipcRenderer.sendSync(IPC_STATUS);
      if (!result?.ok) throw bridgeError(result, "저장 상태를 확인하지 못했습니다.");
      return result.diagnostics;
    },
  }));
} catch (error) {
  contextBridge.exposeInMainWorld("vesperaDesktop", Object.freeze({
    platform: "electron",
    storageReady: false,
    storageError: error?.message ?? "데스크톱 저장소 초기화 실패",
  }));
}
