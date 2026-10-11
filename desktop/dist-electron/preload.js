"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electron', {
    apiCall: (method, endpoint, data) => electron_1.ipcRenderer.invoke('api-call', { method, endpoint, data }),
    startAgent: (user_id, message) => electron_1.ipcRenderer.invoke('start-agent', { user_id, message }),
});
