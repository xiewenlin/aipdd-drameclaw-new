"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("gulongShell", {
  getState: () => ipcRenderer.invoke("desktop:get-state"),
  onState: (listener) => {
    const wrapped = (_event, state) => listener(state);
    ipcRenderer.on("desktop:state", wrapped);
    return () => ipcRenderer.removeListener("desktop:state", wrapped);
  },
  authenticate: (mode) => ipcRenderer.invoke("desktop:authenticate", mode),
  openOfficialPage: (page) => ipcRenderer.invoke("desktop:open-official-page", page),
  createVideoTask: (input) => ipcRenderer.invoke("desktop:create-video-task", input),
  listVideoTasks: () => ipcRenderer.invoke("desktop:list-video-tasks"),
  refreshAccount: () => ipcRenderer.invoke("desktop:refresh-account"),
  navigate: (action) => ipcRenderer.invoke("desktop:navigate", action),
});
