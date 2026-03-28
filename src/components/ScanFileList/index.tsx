import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  X,
  CheckCheck,
  Play,
  ArrowRight,
  FolderInput,
  FilePen,
  FolderOpen,
  Clock,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import type { Operation } from '../../api/types'
import ConfidenceBadge from '../ConfidenceBadge'

// ---------------------------------------------------------------------------
// Shared action helpers (mirrored from ProposedChanges)
// ---------------------------------------------------------------------------
type ActionKind = 'rename' | 'move' | 'move-rename' | 'organize'

function getAction(op: Operation): ActionKind {
  const nameChanged = op.proposed_name !== op.original_name
  const srcDir = op.source_path.includes('/')
    ? op.source_path.substring(0, op.source_path.lastIndexOf('/'))
    : '.'
  const destDir = op.dest_path.replace(/\/$/, '')
  const pathChanged = srcDir !== destDir
  if (nameChanged && pathChanged) return 'move-rename'
  if (nameChanged) return 'rename'
  if (pathChanged) return 'move'
  return 'organize'
}

const ACTION_META: Record<ActionKind, { label: string; color: string; Icon: React.ElementType }> = {
  rename: {
    label: 'Rename',
    color: 'text-blue-400 bg-blue-950/50 border-blue-800',
    Icon: FilePen,
  },
  move: {
    label: 'Move',
    color: 'text-amber-400 bg-amber-950/50 border-amber-800',
    Icon: FolderInput,
  },
  'move-rename': {
    label: 'Move & Rename',
    color: 'text-purple-400 bg-purple-950/50 border-purple-800',
    Icon: FolderOpen,
  },
  organize: {
    label: 'Organize',
    color: 'text-gray-400 bg-gray-800/50 border-gray-700',
    Icon: FolderOpen,
  },
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface ScanFileListProps {
  /** Full paths returned by /list-files */
  files: string[]
  /** Completed operations returned by polling /operations */
  operations: Operation[]
  /** session.processed_files (how many have completed) */
  processedCount: number
  /** Whether the scan is still running */
  isRunning: boolean
  sessionId: string
  onApplied: () => void
  /** Total scan elapsed seconds from the session (set once scan is done) */
  totalElapsed?: number
  /**
   * Label shown on the "currently processing" file row.
   * Defaults to "Analyzing…"
   */
  activeLabel?: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ScanFileList({
  files,
  operations,
  processedCount,
  isRunning,
  sessionId,
  onApplied,
  totalElapsed,
  activeLabel = 'Analyzing…',
}: ScanFileListProps) {
  const queryClient = useQueryClient()

  // Build a lookup: source_path → Operation
  const opByPath = new Map<string, Operation>()
  for (const op of operations) {
    opByPath.set(op.source_path, op)
  }

  // Operations whose source_path isn't in the previewed file list (edge case)
  const extraOps = operations.filter((op) => !files.includes(op.source_path))

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------
  const approveMutation = useMutation({
    mutationFn: (id: string) => api.approveOperation(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        ['operations', sessionId],
        (old: Operation[] | undefined) =>
          old ? old.map((o) => (o.id === updated.id ? updated : o)) : [updated]
      )
    },
  })

  const skipMutation = useMutation({
    mutationFn: (id: string) => api.skipOperation(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        ['operations', sessionId],
        (old: Operation[] | undefined) =>
          old ? old.map((o) => (o.id === updated.id ? updated : o)) : [updated]
      )
    },
  })

  const retryMutation = useMutation({
    mutationFn: (id: string) => api.retryOperation(id),
    onSuccess: (_result, id) => {
      // Optimistically mark the op as pending while the background worker runs
      queryClient.setQueryData(
        ['operations', sessionId],
        (old: Operation[] | undefined) =>
          old
            ? old.map((o) =>
                o.id === id
                  ? { ...o, status: 'pending' as const, error: undefined, elapsed_seconds: undefined }
                  : o
              )
            : old
      )
    },
  })

  const approveAllMutation = useMutation({
    mutationFn: async () => {
      const pending = operations.filter((o) => o.status === 'pending')
      for (const op of pending) await api.approveOperation(op.id)
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['operations', sessionId] }),
  })

  const applyMutation = useMutation({
    mutationFn: () => api.applySession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      queryClient.invalidateQueries({ queryKey: ['operations', sessionId] })
      onApplied()
    },
  })

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function formatElapsed(seconds: number): string {
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return `${m}m ${s}s`
  }

  // ---------------------------------------------------------------------------
  // Derived counts
  // ---------------------------------------------------------------------------
  const approved = operations.filter((o) => o.status === 'approved')
  const total = files.length || operations.length

  // ---------------------------------------------------------------------------
  // Row renderers
  // ---------------------------------------------------------------------------
  function basename(path: string) {
    return path.split('/').pop() ?? path
  }

  function OperationRow({ op }: { op: Operation }) {
    const action = getAction(op)
    const { label, color, Icon } = ACTION_META[action]
    const nameChanged = op.proposed_name !== op.original_name

    return (
      <div
        className={clsx(
          'flex flex-col gap-1.5 rounded-lg border bg-gray-950 px-3 py-2.5 transition-colors',
          op.status === 'approved'
            ? 'border-green-800/50 bg-green-950/20'
            : op.status === 'skipped'
              ? 'border-gray-800 opacity-40'
              : op.status === 'error'
                ? 'border-red-900/60 bg-red-950/10'
                : 'border-gray-800 hover:bg-gray-900'
        )}
      >
        {/* Row 1: action badge + file description + status/actions */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Action badge */}
          <span
            className={clsx(
              'flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium',
              color
            )}
          >
            <Icon className="h-3 w-3" />
            {label}
          </span>

          {/* Main description */}
          <div className="min-w-0 flex-1">
            {action === 'organize' ? (
              <span className="text-xs text-gray-500 truncate" title={op.source_path}>
                {op.original_name}
                <span className="ml-1 text-gray-600">· no rename needed</span>
              </span>
            ) : nameChanged ? (
              <div className="flex items-center gap-1 min-w-0 text-xs">
                <span
                  className="text-gray-400 truncate shrink-0 max-w-[160px]"
                  title={op.original_name}
                >
                  {op.original_name}
                </span>
                <ArrowRight className="h-3 w-3 text-gray-600 shrink-0" />
                <span className="font-mono text-brand-400 truncate" title={op.proposed_name}>
                  {op.proposed_name}
                </span>
                {action === 'move-rename' && (
                  <span
                    className="text-gray-600 truncate ml-1 shrink-0 max-w-[180px]"
                    title={op.dest_path}
                  >
                    · {op.dest_path}
                  </span>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1 min-w-0 text-xs">
                <span
                  className="text-gray-300 truncate shrink-0 max-w-[160px]"
                  title={op.original_name}
                >
                  {op.original_name}
                </span>
                <ArrowRight className="h-3 w-3 text-gray-600 shrink-0" />
                <span className="text-amber-300 truncate" title={op.dest_path}>
                  {op.dest_path}
                </span>
              </div>
            )}
          </div>

          {/* Status / actions */}
          <div className="shrink-0">
            {op.status === 'applied' || op.status === 'undone' ? (
              <span className="badge badge-gray capitalize">{op.status}</span>
            ) : op.status === 'error' ? (
              <div className="flex items-center gap-1">
                <span className="badge badge-red" title={op.error}>
                  Error
                </span>
                <button
                  className="btn-ghost py-1 px-2 text-gray-400 hover:text-white"
                  onClick={() => retryMutation.mutate(op.id)}
                  disabled={retryMutation.isPending}
                  title="Retry analysis"
                >
                  <RefreshCw className={clsx('h-3.5 w-3.5', retryMutation.isPending && 'animate-spin')} />
                </button>
              </div>
            ) : (
              <div className="flex gap-1">
                <button
                  className={clsx(
                    'btn-ghost py-1 px-2',
                    op.status === 'approved' && 'text-green-400'
                  )}
                  onClick={() => approveMutation.mutate(op.id)}
                  title="Approve"
                >
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button
                  className={clsx(
                    'btn-ghost py-1 px-2',
                    op.status === 'skipped' && 'text-red-400'
                  )}
                  onClick={() => skipMutation.mutate(op.id)}
                  title="Skip"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
                <button
                  className="btn-ghost py-1 px-2 text-gray-500 hover:text-white"
                  onClick={() => retryMutation.mutate(op.id)}
                  disabled={retryMutation.isPending}
                  title="Retry analysis"
                >
                  <RefreshCw className={clsx('h-3.5 w-3.5', retryMutation.isPending && 'animate-spin')} />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Row 2: category + confidence + elapsed */}
        <div className="flex items-center gap-2 pl-0.5">
          <span className="badge badge-gray">{op.category}</span>
          <span title={op.ai_reasoning ?? undefined}>
            <ConfidenceBadge value={op.confidence} />
          </span>
          {op.elapsed_seconds != null && (
            <span className="text-xs text-gray-500 tabular-nums flex items-center gap-1" title="LLM processing time">
              <Clock className="h-3 w-3" />
              {formatElapsed(op.elapsed_seconds)}
            </span>
          )}
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">
          {isRunning ? (
            <>
              <span className="text-white font-medium">{processedCount}</span>
              <span> of </span>
              <span className="text-white font-medium">{total}</span>
              <span> analyzed</span>
              {approved.length > 0 && (
                <span className="ml-2 text-brand-400">· {approved.length} approved</span>
              )}
            </>
          ) : (
            <>
              {operations.length} proposed · {approved.length} approved
            </>
          )}
        </p>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            onClick={() => approveAllMutation.mutate()}
            disabled={approveAllMutation.isPending || operations.filter(o => o.status === 'pending').length === 0}
          >
            <CheckCheck className="h-4 w-4" />
            Approve All
          </button>
          <button
            className="btn-primary"
            disabled={approved.length === 0 || applyMutation.isPending || isRunning}
            onClick={() => applyMutation.mutate()}
            title={isRunning ? 'Wait for scan to finish before applying' : undefined}
          >
            <Play className="h-4 w-4" />
            {applyMutation.isPending ? 'Applying…' : `Apply ${approved.length} changes`}
          </button>
        </div>
      </div>

      {/* File list */}
      <div className="flex flex-col gap-1.5">
        {files.map((filePath, idx) => {
          const op = opByPath.get(filePath)

          // Completed — show the full operation result
          if (op) return <OperationRow key={filePath} op={op} />

          // Currently processing
          if (idx === processedCount && isRunning) {
            return (
              <div
                key={filePath}
                className="flex items-center gap-3 rounded-lg border border-brand-700/50 bg-brand-950/20 px-3 py-2.5"
              >
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-brand-400" />
                <span className="min-w-0 flex-1 truncate text-xs text-brand-300" title={filePath}>
                  {basename(filePath)}
                </span>
                <span className="shrink-0 text-xs text-brand-500 animate-pulse">{activeLabel}</span>
              </div>
            )
          }

          // Queued — not yet reached
          return (
            <div
              key={filePath}
              className="flex items-center gap-3 rounded-lg border border-gray-800/50 bg-gray-950/50 px-3 py-2.5 opacity-40"
            >
              <Clock className="h-3.5 w-3.5 shrink-0 text-gray-600" />
              <span className="min-w-0 flex-1 truncate text-xs text-gray-500" title={filePath}>
                {basename(filePath)}
              </span>
            </div>
          )
        })}

        {/* Extra operations whose file wasn't in the preview list */}
        {extraOps.map((op) => (
          <OperationRow key={op.id} op={op} />
        ))}

        {/* Empty state */}
        {files.length === 0 && operations.length === 0 && !isRunning && (
          <div className="flex items-center gap-2 py-10 justify-center text-gray-500 text-sm">
            <AlertCircle className="h-4 w-4" />
            No files found to organize.
          </div>
        )}
      </div>
    </div>
  )
}
