import { spawn, ChildProcess } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'
import * as net from 'net'
import { app } from 'electron'

let sidecarProcess: ChildProcess | null = null

/** Find a free TCP port */
function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (!address || typeof address === 'string') {
        reject(new Error('Could not determine port'))
        return
      }
      const port = address.port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

/** Resolve the Python executable or packaged binary */
function resolvePythonExecutable(): { exe: string; args: string[] } {
  const isPacked = app.isPackaged

  if (isPacked) {
    // Packaged: use the PyInstaller one-file binary from extraResources
    const coreExe = process.platform === 'win32' ? 'core.exe' : 'core'
    const exePath = join(process.resourcesPath, 'core', coreExe)
    return { exe: exePath, args: [] }
  }

  // Development: prefer the local .venv, then fall back to system python
  const appRoot = app.getAppPath()
  const venvPython =
    process.platform === 'win32'
      ? join(appRoot, '.venv', 'Scripts', 'python.exe')
      : join(appRoot, '.venv', 'bin', 'python')

  if (existsSync(venvPython)) {
    return { exe: venvPython, args: ['-m', 'core.main'] }
  }

  // Fallback to system python
  const python = process.platform === 'win32' ? 'python' : 'python3'
  return { exe: python, args: ['-m', 'core.main'] }
}

/** Start the FastAPI sidecar and return the bound port */
export async function startSidecar(): Promise<number> {
  const port = await findFreePort()
  const { exe, args } = resolvePythonExecutable()

  console.log(`[sidecar] Starting backend on port ${port}: ${exe} ${args.join(' ')} --port ${port}`)

  sidecarProcess = spawn(exe, [...args, '--port', String(port)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: app.getAppPath(),
    env: {
      ...process.env,
      CAIBINET_PORT: String(port)
    }
  })

  sidecarProcess.stdout?.on('data', (data) => {
    console.log(`[python] ${data.toString().trimEnd()}`)
  })

  sidecarProcess.stderr?.on('data', (data) => {
    console.log(`[python:err] ${data.toString().trimEnd()}`)
  })

  sidecarProcess.on('exit', (code) => {
    console.log(`[sidecar] Process exited with code ${code}`)
    sidecarProcess = null
  })

  return port
}

/** Poll until the backend is accepting connections (max 30 s) */
export async function waitForBackend(port: number, timeoutMs = 30_000): Promise<void> {
  const start = Date.now()
  const url = `http://127.0.0.1:${port}/health`

  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 300))
  }

  throw new Error(`Backend did not start within ${timeoutMs}ms`)
}

/** Kill the sidecar when the Electron app exits */
export function stopSidecar(): void {
  if (sidecarProcess && !sidecarProcess.killed) {
    console.log('[sidecar] Stopping backend process')
    sidecarProcess.kill()
    sidecarProcess = null
  }
}
