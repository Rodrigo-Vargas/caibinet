import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron'
import { join } from 'path'
import { startSidecar, stopSidecar, waitForBackend } from './sidecar'

let mainWindow: BrowserWindow | null = null
let backendPort: number | null = null

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Caibinet',
    webPreferences: {

    preload: join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    show: false
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  if (process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  // Register IPC handlers before creating window
  ipcMain.handle('get-backend-port', () => backendPort)

  ipcMain.handle('open-file', async (_event, filePath: string) => {
    const error = await shell.openPath(filePath)
    return error === '' ? null : error
  })

  ipcMain.handle('select-directory', async () => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ['openDirectory'],
      title: 'Select a folder to organize'
    })
    return result.canceled ? null : result.filePaths[0]
  })

  try {
    // Start Python sidecar
    backendPort = await startSidecar()
    await waitForBackend(backendPort)
  } catch (err) {
    console.error('[main] Backend failed to start:', err)
    // Continue anyway — UI will show a connection error
  }

  await createWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('will-quit', () => {
  stopSidecar()
})

app.on('activate', async () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    await createWindow()
  }
})
