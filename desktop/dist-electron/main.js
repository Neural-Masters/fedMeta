"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
let mainWindow = null;
function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
            preload: path_1.default.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
        title: 'FedMeta Desktop',
        icon: path_1.default.join(__dirname, '../public/icon.png'),
    });
    // In dev, load from Vite dev server
    // In production, load from built files
    if (process.env.VITE_DEV_SERVER_URL) {
        mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
        mainWindow.webContents.openDevTools();
    }
    else {
        mainWindow.loadFile(path_1.default.join(__dirname, '../dist/index.html'));
    }
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}
electron_1.app.whenReady().then(() => {
    createWindow();
    electron_1.app.on('activate', () => {
        if (electron_1.BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});
electron_1.app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        electron_1.app.quit();
    }
});
// IPC handlers for Python backend communication
electron_1.ipcMain.handle('api-call', async (_event, { method, endpoint, data }) => {
    try {
        const response = await fetch(`http://localhost:8000${endpoint}`, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: data ? JSON.stringify(data) : undefined,
        });
        return { ok: true, data: await response.json() };
    }
    catch (error) {
        return { ok: false, error: error.message };
    }
});
electron_1.ipcMain.handle('start-agent', async (_event, { user_id, message }) => {
    try {
        const response = await fetch('http://localhost:8000/agent/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, message }),
        });
        return { ok: true, data: await response.json() };
    }
    catch (error) {
        return { ok: false, error: error.message };
    }
});
