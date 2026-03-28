import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, ChevronDown, ChevronRight } from 'lucide-react'
import { api } from '../../api/client'
import type { Session, Operation } from '../../api/types'
import ConfidenceBadge from '../ConfidenceBadge'

interface UndoHistoryProps {
  sessions: Session[]
  operationsBySession: Record<string, Operation[]>
}

export default function UndoHistory({ sessions, operationsBySession }: UndoHistoryProps) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const undoSessionMutation = useMutation({
    mutationFn: (sessionId: string) => api.undoSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      queryClient.invalidateQueries({ queryKey: ['operations'] })
    }
  })

  const undoOpMutation = useMutation({
    mutationFn: (opId: string) => api.undoOperation(opId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['operations'] })
    }
  })

  if (sessions.length === 0) {
    return (
      <div className="py-20 text-center text-gray-500">
        No sessions yet. Run a scan on the Dashboard.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {sessions.map((session) => {
        const ops = operationsBySession[session.id] ?? []
        const isExpanded = expanded.has(session.id)
        const appliedOps = ops.filter((o) => o.status === 'applied')

        return (
          <div key={session.id} className="card overflow-hidden">
            {/* Session header */}
            <div className="flex items-center gap-3">
              <button
                className="btn-ghost py-1 px-1"
                onClick={() => toggle(session.id)}
              >
                {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-200 truncate">{session.directory}</p>
                <p className="text-xs text-gray-500">
                  {new Date(session.created_at).toLocaleString()} · {ops.length} files ·&nbsp;
                  <span className="capitalize">{session.status}</span>
                </p>
              </div>

              {appliedOps.length > 0 && (
                <button
                  className="btn-secondary text-xs"
                  onClick={() => undoSessionMutation.mutate(session.id)}
                  disabled={undoSessionMutation.isPending}
                  title="Undo all applied operations for this session"
                >
                  <RotateCcw className="h-3 w-3" />
                  Undo session
                </button>
              )}
            </div>

            {/* Operations list */}
            {isExpanded && ops.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-800 text-gray-500">
                      <th className="pb-2 text-left font-medium">File</th>
                      <th className="pb-2 text-left font-medium">Proposed</th>
                      <th className="pb-2 text-left font-medium">Confidence</th>
                      <th className="pb-2 text-left font-medium">Status</th>
                      <th className="pb-2 font-medium" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/50">
                    {ops.map((op) => (
                      <tr key={op.id} className="py-1">
                        <td className="py-1.5 text-gray-300 max-w-[200px] truncate" title={op.source_path}>
                          {op.original_name}
                        </td>
                        <td className="py-1.5 text-brand-400 font-mono max-w-[200px] truncate" title={op.dest_path}>
                          {op.proposed_name}
                        </td>
                        <td className="py-1.5">
                          <ConfidenceBadge value={op.confidence} />
                        </td>
                        <td className="py-1.5">
                          <span className="badge badge-gray capitalize">{op.status}</span>
                        </td>
                        <td className="py-1.5 text-right">
                          {op.status === 'applied' && (
                            <button
                              className="btn-ghost py-0.5 px-1.5 text-xs"
                              onClick={() => undoOpMutation.mutate(op.id)}
                              disabled={undoOpMutation.isPending}
                            >
                              <RotateCcw className="h-3 w-3" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
