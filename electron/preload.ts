import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendPort: (): Promise<number> => ipcRenderer.invoke('get-backend-port'),
  selectDirectory: (): Promise<string | null> => ipcRenderer.invoke('select-directory')
})

// TypeScript declaration for renderer-side usage
declare global {
  interface Window {
    electronAPI: {
      getBackendPort: () => Promise<number>
      selectDirectory: () => Promise<string | null>
    }
  }
}
