import type {
  Session,
  Operation,
  Settings,
  ScanRequest,
  ScanResponse,
  UndoResult,
  ApplyResult,
  HealthResponse,
  LLMHealthResponse,
  FileListResponse,
  FilePreviewResponse
} from './types'

// ---------------------------------------------------------------------------
// Port resolution — reads from Electron bridge or falls back to env (dev mode)
// ---------------------------------------------------------------------------
let _cachedPort: number | null = null

async function getPort(): Promise<number> {
  if (_cachedPort !== null) return _cachedPort

  if (typeof window !== 'undefined' && window.electronAPI) {
    _cachedPort = await window.electronAPI.getBackendPort()
  } else {
    _cachedPort = Number(import.meta.env.VITE_BACKEND_PORT ?? 8765)
  }

  return _cachedPort
}
async function base(): Promise<string> {
  const port = await getPort()
  return `http://127.0.0.1:${port}`
}

// ---------------------------------------------------------------------------
// Generic request helper
// ---------------------------------------------------------------------------
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${await base()}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }

  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------
export const api = {
  // Health
  health: () => request<HealthResponse>('/health'),
  llmHealth: () => request<LLMHealthResponse>('/health/llm'),
  checkLLMHealth: (ollama_url: string, ollama_model: string) =>
    request<LLMHealthResponse>('/health/llm/check', {
      method: 'POST',
      body: JSON.stringify({ ollama_url, ollama_model })
    }),

  // Scan
  scan: (body: ScanRequest) =>
    request<ScanResponse>('/scan', { method: 'POST', body: JSON.stringify(body) }),

  listFiles: (directory: string) => {
    const qs = new URLSearchParams({ directory }).toString()
    return request<FileListResponse>(`/list-files?${qs}`)
  },

  // Sessions
  getSessions: () => request<Session[]>('/sessions'),

  getSession: (sessionId: string) => request<Session>(`/sessions/${sessionId}`),

  applySession: (sessionId: string) =>
    request<ApplyResult>(`/sessions/${sessionId}/apply`, { method: 'POST' }),

  cancelSession: (sessionId: string) =>
    request<{ session_id: string; message: string }>(`/sessions/${sessionId}/cancel`, { method: 'POST' }),

  // Operations
  getOperations: (params?: { session_id?: string; status?: string }) => {
    const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
    return request<Operation[]>(`/operations${qs}`)
  },

  approveOperation: (id: string) =>
    request<Operation>(`/operations/${id}/approve`, { method: 'POST' }),

  skipOperation: (id: string) =>
    request<Operation>(`/operations/${id}/skip`, { method: 'POST' }),

  retryOperation: (id: string) =>
    request<{ op_id: string; message: string }>(`/operations/${id}/retry`, { method: 'POST' }),

  // Undo
  undoOperation: (id: string) =>
    request<UndoResult>(`/undo/${id}`, { method: 'POST' }),

  undoSession: (sessionId: string) =>
    request<UndoResult[]>(`/undo/session/${sessionId}`, { method: 'POST' }),

  undoAll: () => request<UndoResult[]>('/undo/all', { method: 'POST' }),

  // Settings
  getSettings: () => request<Settings>('/settings'),

  putSettings: (settings: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(settings) }),

  // Ollama model list (proxied through backend)
  listModels: () => request<string[]>('/settings/models'),

  // Ollama vision-capable model list (models with "clip" in their families)
  listVisionModels: () => request<string[]>('/settings/vision-models'),

  // Cache
  clearSummaryCache: () =>
    request<{ deleted: number }>('/cache/summary', { method: 'DELETE' }),

  // File preview
  previewFile: (path: string) => {
    const qs = new URLSearchParams({ path }).toString()
    return request<FilePreviewResponse>(`/preview?${qs}`)
  }
}
