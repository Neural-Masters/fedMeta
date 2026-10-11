import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electron', {
  apiCall: (method: string, endpoint: string, data?: any) =>
    ipcRenderer.invoke('api-call', { method, endpoint, data }),
  startAgent: (user_id: string, message: string) =>
    ipcRenderer.invoke('start-agent', { user_id, message }),
})
