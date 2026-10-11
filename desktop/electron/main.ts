import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'path'

let mainWindow: BrowserWindow | null = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: 'FedMeta Desktop',
    icon: path.join(__dirname, '../public/icon.png'),
  })

  // In dev, load from Vite dev server
  // In production, load from built files
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// IPC handlers for Python backend communication
ipcMain.handle('api-call', async (_event, { method, endpoint, data }: {
  method: string
  endpoint: string
  data?: any
}) => {
  try {
    const response = await fetch(`http://localhost:8000${endpoint}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    })
    return { ok: true, data: await response.json() }
  } catch (error: any) {
    return { ok: false, error: error.message }
  }
})

ipcMain.handle('start-agent', async (_event, { user_id, message }: {
  user_id: string
  message: string
}) => {
  try {
    const response = await fetch('http://localhost:8000/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, message }),
    })
    return { ok: true, data: await response.json() }
  } catch (error: any) {
    return { ok: false, error: error.message }
  }
})
