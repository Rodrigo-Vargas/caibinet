import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Scan, AlertCircle, WifiOff, Square } from 'lucide-react'
import { api } from '../api/client'
import ScanFileList from '../components/ScanFileList'
import ScanPhaseStepper from '../components/ScanPhaseStepper'
import { useAppStore } from '../store/appStore'
import type { Operation } from '../api/types'

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { llmStatus, llmStatusDetail } = useAppStore()
  const [directory, setDirectory] = useState('/home/rodrigo/Work/caibinet/tests/fixtures')
  const [dryRun, setDryRun] = useState(true)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [fileList, setFileList] = useState<string[]>([])

  // Live elapsed timer — starts when scan begins, locks to server value when done
  const [elapsedLive, setElapsedLive] = useState<number | null>(null)
  const scanStartRef = useRef<number | null>(null)

  // Poll session status while scanning
  const { data: session } = useQuery({
    queryKey: ['sessions', activeSessionId],
    queryFn: () => api.getSession(activeSessionId!),
    enabled: !!activeSessionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 1000 : false
    }
  })

  // Operations for the active session — poll while scan is running so results
  // appear in the UI as soon as the LLM returns each file's proposal.
  const { data: operations = [] } = useQuery({
    queryKey: ['operations', activeSessionId],
    queryFn: () => api.getOperations({ session_id: activeSessionId! }),
    enabled: !!activeSessionId,
    refetchInterval: (query) => {
      // Keep polling while the session is actively scanning
      const sessionStatus = session?.status
      if (sessionStatus === 'running' || sessionStatus === 'pending') return 1000
      // Also keep polling if any operation is still pending (e.g. a retry running in the background)
      const ops = query.state.data as Operation[] | undefined
      if (ops?.some((op) => op.status === 'pending')) return 1000
      // One final refetch after reaching a terminal state (handled by query invalidation below)
      return false
    }
  })

  // Final refresh once the scan fully completes to capture any last operations
  useEffect(() => {
    if (!activeSessionId || !session) return
    const terminal = ['applied', 'pending', 'error', 'cancelled']
    if (terminal.includes(session.status)) {
      queryClient.invalidateQueries({ queryKey: ['operations', activeSessionId] })
    }
  }, [session?.status, activeSessionId])

  const scanMutation = useMutation({
    mutationFn: () =>
      Promise.all([
        api.scan({ directory, dry_run: dryRun }),
        api.listFiles(directory),
      ]),
    onMutate: () => {
      setScanError(null)
      setFileList([])
    },
    onSuccess: ([scanRes, listRes]) => {
      setActiveSessionId(scanRes.session_id)
      setFileList(listRes.files)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
    onError: (err: Error) => setScanError(err.message)
  })

  // Live elapsed clock: tick while scanning, lock to server value when done
  const isScanActive = scanMutation.isPending || (session?.status === 'running') || (session?.status === 'pending')
  useEffect(() => {
    if (isScanActive) {
      if (scanStartRef.current === null) {
        scanStartRef.current = Date.now()
        setElapsedLive(0)
      }
      const id = setInterval(() => {
        setElapsedLive(Math.floor((Date.now() - scanStartRef.current!) / 1000))
      }, 1000)
      return () => clearInterval(id)
    } else if (session?.elapsed_seconds != null) {
      // Scan ended — lock to the precise server-side duration
      setElapsedLive(session.elapsed_seconds)
      scanStartRef.current = null
    } else if (!activeSessionId) {
      // No active scan at all — reset
      setElapsedLive(null)
      scanStartRef.current = null
    }
  }, [isScanActive, session?.elapsed_seconds, activeSessionId])

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelSession(activeSessionId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions', activeSessionId] })
      queryClient.invalidateQueries({ queryKey: ['operations', activeSessionId] })
    }
  })

  const handleSelectDir = async () => {
    const picked = await window.electronAPI.selectDirectory()
    if (picked) setDirectory(picked)
  }

  const isRunning = session?.status === 'pending' || session?.status === 'running'
  const isCancelled = session?.status === 'cancelled'
  const isSummarizing = isRunning && session?.phase === 'summarizing'

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Organize Files</h1>
        <p className="text-sm text-gray-400 mt-1">
          Select a folder and let the AI propose an organized structure.
        </p>
      </div>

      {/* Scan controls */}
      <div className="card space-y-4">
        <div className="flex gap-2">
          <input
            className="input flex-1"
            value={directory}
            onChange={(e) => setDirectory(e.target.value)}
            placeholder="/home/user/Documents/messy-folder"
            readOnly
          />
          <button className="btn-secondary flex-none" onClick={handleSelectDir}>
            <FolderOpen className="h-4 w-4" />
            Browse
          </button>
        </div>

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              className="rounded text-brand-600"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Dry run (only propose, don't move files)
          </label>

          <button
            className="btn-primary"
            disabled={!directory || scanMutation.isPending || isRunning || llmStatus === 'error'}
            onClick={() => scanMutation.mutate()}
            title={llmStatus === 'error' ? 'LLM is unavailable — fix your Ollama settings first' : undefined}
          >
            <Scan className="h-4 w-4" />
            {scanMutation.isPending || isRunning ? 'Scanning…' : 'Scan'}
          </button>
          {isRunning && (
            <button
              className="btn-secondary flex-none text-red-400 hover:text-red-300 border-red-800 hover:border-red-600"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              title="Stop processing"
            >
              <Square className="h-4 w-4" />
              {cancelMutation.isPending ? 'Stopping…' : 'Stop'}
            </button>
          )}
        </div>

        {/* LLM unavailable notice */}
        {llmStatus === 'error' && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-950/50 border border-amber-800 px-3 py-2 text-sm text-amber-400">
            <WifiOff className="h-4 w-4 mt-0.5 flex-none" />
            <span>
              <span className="font-medium">LLM unavailable:</span> {llmStatusDetail}
            </span>
          </div>
        )}

        {/* Scan error */}
        {scanError && llmStatus !== 'error' && (
          <div className="flex items-start gap-2 rounded-lg bg-red-950/50 border border-red-800 px-3 py-2 text-sm text-red-400">
            <AlertCircle className="h-4 w-4 mt-0.5 flex-none" />
            {scanError}
          </div>
        )}
      </div>

      {/* Phase stepper — shown as soon as a session starts and stays visible through completion */}
      {activeSessionId && session && (
        <ScanPhaseStepper
          isRunning={isRunning}
          phase={session.phase}
          totalFiles={session.total_files}
          processedFiles={session.processed_files}
          isCancelled={isCancelled}
          elapsed={elapsedLive ?? undefined}
        />
      )}

      {/* Phase 2 — "Proposed Changes" per-file results (shown once deciding starts) */}
      {activeSessionId && !isSummarizing && (fileList.length > 0 || operations.length > 0) && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-white">Proposed Changes</h2>
            {isCancelled && (
              <span className="flex items-center gap-1.5 text-xs text-gray-400">
                <Square className="h-3 w-3" />
                Stopped — partial results
              </span>
            )}
          </div>
          <ScanFileList
            files={fileList}
            operations={operations}
            processedCount={session?.processed_files ?? 0}
            isRunning={isRunning && !isSummarizing}
            sessionId={activeSessionId}
            totalElapsed={elapsedLive ?? undefined}
            activeLabel="Reviewing…"
            onApplied={() => {
              queryClient.invalidateQueries({ queryKey: ['operations', activeSessionId] })
            }}
          />
        </div>
      )}

      {/* Empty state after scan */}
      {activeSessionId && fileList.length === 0 && operations.length === 0 && !isRunning && (
        <div className="py-16 text-center text-gray-500">
          No changes proposed. All files may have been skipped (low confidence or already organized).
        </div>
      )}
    </div>
  )
}
