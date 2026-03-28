import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import UndoHistory from '../components/UndoHistory'
import type { Operation } from '../api/types'

export default function History() {
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: api.getSessions,
    refetchInterval: 5_000
  })

  // Fetch operations for all sessions (paginated in future; flat for now)
  const { data: allOperations = [] } = useQuery({
    queryKey: ['operations'],
    queryFn: () => api.getOperations(),
    enabled: sessions.length > 0
  })

  // Group by session
  const bySession = allOperations.reduce<Record<string, Operation[]>>((acc, op) => {
    if (!acc[op.session_id]) acc[op.session_id] = []
    acc[op.session_id].push(op)
    return acc
  }, {})

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">History</h1>
        <p className="text-sm text-gray-400 mt-1">
          Review past sessions and undo individual or batch file moves.
        </p>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-gray-500">Loading…</div>
      ) : (
        <UndoHistory sessions={sessions} operationsBySession={bySession} />
      )}
    </div>
  )
}
