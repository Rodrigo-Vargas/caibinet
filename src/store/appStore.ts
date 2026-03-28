import { create } from 'zustand'
import type { Session, Operation } from '../api/types'

export type LLMStatus = 'unknown' | 'ok' | 'error'

interface AppState {
  // Active session being scanned/reviewed
  activeSessionId: string | null
  setActiveSessionId: (id: string | null) => void

  // Operations for the active session
  operations: Operation[]
  setOperations: (ops: Operation[]) => void
  updateOperation: (op: Operation) => void

  // Sessions list
  sessions: Session[]
  setSessions: (sessions: Session[]) => void

  // Scan progress
  isScanning: boolean
  setIsScanning: (v: boolean) => void

  // LLM health
  llmStatus: LLMStatus
  llmStatusDetail: string
  setLLMStatus: (status: LLMStatus, detail?: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  activeSessionId: null,
  setActiveSessionId: (id) => set({ activeSessionId: id }),

  operations: [],
  setOperations: (ops) => set({ operations: ops }),
  updateOperation: (op) =>
    set((state) => ({
      operations: state.operations.map((o) => (o.id === op.id ? op : o))
    })),

  sessions: [],
  setSessions: (sessions) => set({ sessions }),

  isScanning: false,
  setIsScanning: (v) => set({ isScanning: v }),

  llmStatus: 'unknown',
  llmStatusDetail: '',
  setLLMStatus: (status, detail = '') => set({ llmStatus: status, llmStatusDetail: detail })
}))
