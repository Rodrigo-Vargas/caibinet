import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X, CheckCheck, Play, ArrowRight, FolderInput, FilePen, FolderOpen } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import type { Operation } from '../../api/types'
import ConfidenceBadge from '../ConfidenceBadge'

interface ProposedChangesProps {
  operations: Operation[]
  sessionId: string
  onApplied: () => void
}

type ActionKind = 'rename' | 'move' | 'move-rename' | 'organize'

function getAction(op: Operation): ActionKind {
  const nameChanged = op.proposed_name !== op.original_name
  // source_path is the full file path; dest_path is the destination directory
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
  rename:      { label: 'Rename',      color: 'text-blue-400 bg-blue-950/50 border-blue-800',   Icon: FilePen },
  move:        { label: 'Move',        color: 'text-amber-400 bg-amber-950/50 border-amber-800', Icon: FolderInput },
  'move-rename': { label: 'Move & Rename', color: 'text-purple-400 bg-purple-950/50 border-purple-800', Icon: FolderOpen },
  organize:    { label: 'Organize',    color: 'text-gray-400 bg-gray-800/50 border-gray-700',   Icon: FolderOpen },
}

export default function ProposedChanges({ operations, sessionId, onApplied }: ProposedChangesProps) {
  const queryClient = useQueryClient()

  const approveMutation = useMutation({
    mutationFn: (id: string) => api.approveOperation(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(['operations', sessionId], (old: Operation[] | undefined) =>
        old ? old.map((o) => (o.id === updated.id ? updated : o)) : [updated]
      )
    }
  })

  const skipMutation = useMutation({
    mutationFn: (id: string) => api.skipOperation(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(['operations', sessionId], (old: Operation[] | undefined) =>
        old ? old.map((o) => (o.id === updated.id ? updated : o)) : [updated]
      )
    }
  })

  const applyMutation = useMutation({
    mutationFn: () => api.applySession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      queryClient.invalidateQueries({ queryKey: ['operations', sessionId] })
      onApplied()
    }
  })

  const approveAllMutation = useMutation({
    mutationFn: async () => {
      const pending = operations.filter((o) => o.status === 'pending')
      for (const op of pending) {
        await api.approveOperation(op.id)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['operations', sessionId] })
    }
  })

  const approved = operations.filter((o) => o.status === 'approved')
  const hasApproved = approved.length > 0

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">
          {operations.length} proposed · {approved.length} approved
        </p>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            onClick={() => approveAllMutation.mutate()}
            disabled={approveAllMutation.isPending}
          >
            <CheckCheck className="h-4 w-4" />
            Approve All
          </button>
          <button
            className="btn-primary"
            disabled={!hasApproved || applyMutation.isPending}
            onClick={() => applyMutation.mutate()}
          >
            <Play className="h-4 w-4" />
            {applyMutation.isPending ? 'Applying…' : `Apply ${approved.length} changes`}
          </button>
        </div>
      </div>

      {/* List */}
      <div className="flex flex-col gap-2">
        {operations.map((op) => {
          const action = getAction(op)
          const { label, color, Icon } = ACTION_META[action]
          const nameChanged = op.proposed_name !== op.original_name

          return (
            <div
              key={op.id}
              className={clsx(
                'flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-950 px-3 py-2.5 transition-colors hover:bg-gray-900',
                op.status === 'approved' && 'border-green-800/50 bg-green-950/20',
                op.status === 'skipped' && 'opacity-40'
              )}
            >
              {/* Action badge */}
              <span className={clsx('flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium', color)}>
                <Icon className="h-3 w-3" />
                {label}
              </span>

              {/* Main description */}
              <div className="min-w-0 flex-1">
                {action === 'organize' ? (
                  // Same name, same location — de-emphasised
                  <span className="text-xs text-gray-500 truncate" title={op.source_path}>
                    {op.original_name}
                    <span className="ml-1 text-gray-600">· no rename needed</span>
                  </span>
                ) : nameChanged ? (
                  // Show old → new name
                  <div className="flex items-center gap-1 min-w-0 text-xs">
                    <span className="text-gray-400 truncate shrink-0 max-w-[160px]" title={op.original_name}>
                      {op.original_name}
                    </span>
                    <ArrowRight className="h-3 w-3 text-gray-600 shrink-0" />
                    <span className="font-mono text-brand-400 truncate" title={op.proposed_name}>
                      {op.proposed_name}
                    </span>
                    {action === 'move-rename' && (
                      <span className="text-gray-600 truncate ml-1 shrink-0 max-w-[180px]" title={op.dest_path}>
                        · {op.dest_path}
                      </span>
                    )}
                  </div>
                ) : (
                  // Move only — same name, new location
                  <div className="flex items-center gap-1 min-w-0 text-xs">
                    <span className="text-gray-300 truncate shrink-0 max-w-[160px]" title={op.original_name}>
                      {op.original_name}
                    </span>
                    <ArrowRight className="h-3 w-3 text-gray-600 shrink-0" />
                    <span className="text-amber-300 truncate" title={op.dest_path}>
                      {op.dest_path}
                    </span>
                  </div>
                )}
              </div>

              {/* Category + confidence */}
              <div className="flex shrink-0 items-center gap-2">
                <span className="badge badge-gray">{op.category}</span>
                <span title={op.ai_reasoning ?? undefined}>
                  <ConfidenceBadge value={op.confidence} />
                </span>
              </div>

              {/* Actions */}
              <div className="shrink-0">
                {op.status === 'applied' || op.status === 'undone' ? (
                  <span className="badge badge-gray capitalize">{op.status}</span>
                ) : op.status === 'error' ? (
                  <span className="badge badge-red" title={op.error}>Error</span>
                ) : (
                  <div className="flex gap-1">
                    <button
                      className={clsx('btn-ghost py-1 px-2', op.status === 'approved' && 'text-green-400')}
                      onClick={() => approveMutation.mutate(op.id)}
                      title="Approve"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      className={clsx('btn-ghost py-1 px-2', op.status === 'skipped' && 'text-red-400')}
                      onClick={() => skipMutation.mutate(op.id)}
                      title="Skip"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {operations.length === 0 && (
          <div className="py-12 text-center text-gray-500">No changes proposed</div>
        )}
      </div>
    </div>
  )
}
