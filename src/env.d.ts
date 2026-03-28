/// <reference types="vite/client" />

interface Window {
  electronAPI: {
    getBackendPort: () => Promise<number>
    selectDirectory: () => Promise<string | null>
  }
}

interface ImportMetaEnv {
  readonly VITE_BACKEND_PORT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
