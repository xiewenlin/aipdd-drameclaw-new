"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// A narrow bridge is exposed for the hosted app. It contains no raw IPC,
// filesystem, cookie, token, or shell primitives.
contextBridge.exposeInMainWorld("gulongDesktop", {
  isDesktop: true,
  platform: process.platform,
  requestAuth: (mode) => ipcRenderer.invoke("desktop:authenticate", mode),
  openAccount: () => ipcRenderer.invoke("desktop:open-official-page", "account"),
  openSubscription: () => ipcRenderer.invoke("desktop:open-official-page", "subscription"),
  openRecharge: () => ipcRenderer.invoke("desktop:open-official-page", "recharge"),
  listVideoTasks: () => ipcRenderer.invoke("desktop:list-video-tasks"),
});
