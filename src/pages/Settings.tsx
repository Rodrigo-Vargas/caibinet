import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import type { Settings } from '../api/types'
import { useAppStore } from '../store/appStore'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { setLLMStatus } = useAppStore()
  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings
  })

  const { data: models = [], refetch: refetchModels, isFetching: modelsLoading } = useQuery({
    queryKey: ['models'],
    queryFn: api.listModels,
    retry: false
  })

  const [form, setForm] = useState<Settings>({
    ollama_url: 'http://localhost:11434',
    ollama_model: 'llama3',
    ollama_timeout: 120,
    ignore_patterns: ['*.tmp', '*.log', '.DS_Store', 'node_modules/**'],
    max_files: 1,
    context_aware: false,
    summary_cache_ttl_minutes: 1440,
  })

  const [pingStatus, setPingStatus] = useState<'idle' | 'ok' | 'err'>('idle')
  const [ignorePatternsText, setIgnorePatternsText] = useState('')

  useEffect(() => {
    if (settings) {
      setForm(settings)
      setIgnorePatternsText(settings.ignore_patterns.join('\n'))
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: (data: Partial<Settings>) => api.putSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['models'] })
      // Re-check LLM health immediately with the new settings
      api.llmHealth().then((res) => {
        setLLMStatus(res.ok ? 'ok' : 'error', res.detail)
      }).catch(() => {
        setLLMStatus('error', 'Could not reach the backend')
      })
    }
  })

  const handleSave = () => {
    saveMutation.mutate({
      ...form,
      ignore_patterns: ignorePatternsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
    })
  }

  const handlePing = async () => {
    setPingStatus('idle')
    try {
      const res = await api.checkLLMHealth(form.ollama_url, form.ollama_model)
      setPingStatus(res.ok ? 'ok' : 'err')
      setLLMStatus(res.ok ? 'ok' : 'error', res.detail)
    } catch {
      setPingStatus('err')
      setLLMStatus('error', 'Could not reach the backend')
    }
  }

  if (isLoading) {
    return <div className="py-16 text-center text-gray-500">Loading…</div>
  }

  return (
    <div className="space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-400 mt-1">
          Configure the AI backend and ignore rules.
        </p>
      </div>

      {/* Ollama section */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
          Ollama / LLM
        </h2>

        <div className="space-y-1">
          <label className="text-xs text-gray-400">Ollama URL</label>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              value={form.ollama_url}
              onChange={(e) => setForm((f) => ({ ...f, ollama_url: e.target.value }))}
              placeholder="http://localhost:11434"
            />
            <button className="btn-secondary flex-none" onClick={handlePing}>
              {pingStatus === 'idle' ? (
                <>
                  <RefreshCw className="h-4 w-4" /> Test
                </>
              ) : pingStatus === 'ok' ? (
                <>
                  <CheckCircle className="h-4 w-4 text-green-400" /> Connected
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-red-400" /> Failed
                </>
              )}
            </button>
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400">Model</label>
            <button
              type="button"
              className="text-gray-500 hover:text-gray-300 transition-colors"
              onClick={() => refetchModels()}
              title="Refresh model list"
            >
              <RefreshCw className={`h-3 w-3 ${modelsLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
          {models.length > 0 ? (
            <select
              className="input"
              value={form.ollama_model}
              onChange={(e) => setForm((f) => ({ ...f, ollama_model: e.target.value }))}
            >
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              value={form.ollama_model}
              onChange={(e) => setForm((f) => ({ ...f, ollama_model: e.target.value }))}
              placeholder="llama3"
            />
          )}
        </div>
      </section>

      {/* Scan limits */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
          Scan Limits
        </h2>
        <div className="space-y-1">
          <label className="text-xs text-gray-400">Max files per scan</label>
          <p className="text-xs text-gray-500">Limit how many files are sent to the LLM. Set to 0 for no limit.</p>
          <input
            type="number"
            min={0}
            className="input w-32"
            value={form.max_files}
            onChange={(e) => setForm((f) => ({ ...f, max_files: Math.max(0, parseInt(e.target.value) || 0) }))}
          />
        </div>
      </section>

      {/* Context-aware mode */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
          Organisation Behaviour
        </h2>
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-gray-600 bg-gray-800 text-brand-500 focus:ring-brand-500"
            checked={form.context_aware}
            onChange={(e) => setForm((f) => ({ ...f, context_aware: e.target.checked }))}
          />
          <div>
            <p className="text-sm text-gray-200 font-medium">Context-aware mode</p>
            <p className="text-xs text-gray-500 mt-0.5">
              When enabled, the AI receives the full list of files being scanned
              and applies a more conservative strategy for small folders — avoiding
              unnecessary moves when there are 5 files or fewer.
            </p>
          </div>
        </label>

        <div className="space-y-1 pt-2 border-t border-gray-700">
          <label className="text-xs text-gray-400">Summary cache TTL (minutes)</label>
          <p className="text-xs text-gray-500">
            The AI-generated content summary for each file is cached by its hash to avoid
            redundant LLM calls on future scans. Set to <span className="font-mono">0</span> to
            disable caching.
          </p>
          <input
            type="number"
            min={0}
            className="input w-32"
            value={form.summary_cache_ttl_minutes}
            onChange={(e) =>
              setForm((f) => ({ ...f, summary_cache_ttl_minutes: Math.max(0, parseInt(e.target.value) || 0) }))
            }
          />
        </div>
      </section>

      {/* Ignore patterns */}
      <section className="card space-y-4">
        <h2 className="text-sm font-semibold text-gray-200 uppercase tracking-wide">
          Ignore Patterns
        </h2>
        <p className="text-xs text-gray-500">
          One glob pattern per line. Matching files will be excluded from scans.
        </p>
        <textarea
          className="input font-mono text-xs"
          rows={6}
          value={ignorePatternsText}
          onChange={(e) => setIgnorePatternsText(e.target.value)}
        />
      </section>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save settings'}
        </button>
        {saveMutation.isSuccess && (
          <span className="text-sm text-green-400 flex items-center gap-1">
            <CheckCircle className="h-4 w-4" /> Saved
          </span>
        )}
        {saveMutation.isError && (
          <span className="text-sm text-red-400 flex items-center gap-1">
            <XCircle className="h-4 w-4" /> Failed to save
          </span>
        )}
      </div>
    </div>
  )
}
