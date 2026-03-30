import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendPort: (): Promise<number> => ipcRenderer.invoke('get-backend-port'),
  selectDirectory: (): Promise<string | null> => ipcRenderer.invoke('select-directory'),
  openFile: (filePath: string): Promise<string | null> => ipcRenderer.invoke('open-file', filePath)
})

// TypeScript declaration for renderer-side usage
declare global {
  interface Window {
    electronAPI: {
      getBackendPort: () => Promise<number>
      selectDirectory: () => Promise<string | null>
      openFile: (filePath: string) => Promise<string | null>
    }
  }
}
