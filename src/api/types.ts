// ──────────────────────────────────────────────────────────────────────────────
// Shared TypeScript types that mirror the Python Pydantic models
// ──────────────────────────────────────────────────────────────────────────────

export type SessionStatus = 'pending' | 'running' | 'applied' | 'undone' | 'error' | 'cancelled'
export type OperationStatus = 'pending' | 'approved' | 'applied' | 'undone' | 'skipped' | 'error'

/** Phase of the two-step scan pipeline.
 *  - `summarizing`: phase 1 — collecting file content summaries (bulk progress bar shown)
 *  - `deciding`:    phase 2 — per-file rename check + folder organization (results appear per file)
 *  - `null`:        scan is complete or not yet started
 */
export type SessionPhase = 'summarizing' | 'deciding'

export interface Session {
  id: string
  created_at: string
  label: string
  directory: string
  status: SessionStatus
  total_files: number
  processed_files: number
  elapsed_seconds?: number
  phase?: SessionPhase | null
}

export interface Operation {
  id: string
  session_id: string
  created_at: string
  source_path: string
  dest_path: string
  original_name: string
  proposed_name: string
  category: string
  ai_reasoning: string
  confidence: number
  file_hash: string
  status: OperationStatus
  error?: string
  elapsed_seconds?: number
  content_summary?: string
}

export interface Settings {
  ollama_url: string
  ollama_model: string
  ollama_timeout: number
  ignore_patterns: string[]
  max_files: number
  context_aware: boolean
  summary_cache_ttl_minutes: number
  ocr_enabled: boolean
  image_model: string
}

export interface ScanRequest {
  directory: string
  dry_run: boolean
}

export interface ScanResponse {
  session_id: string
  message: string
}

export interface UndoResult {
  operation_id: string
  success: boolean
  error?: string
}

export interface ApplyResult {
  session_id: string
  applied: number
  failed: number
  results: UndoResult[]
}

export interface FileListResponse {
  files: string[]
}

export interface HealthResponse {
  status: string
  version: string
}

export interface LLMHealthResponse {
  ok: boolean
  detail: string
  model: string
  ollama_url: string
}

export interface FilePreviewResponse {
  content: string
  is_binary: boolean
  size: number
  truncated: boolean
  mime_type: string
}
