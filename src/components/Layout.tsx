import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { FolderSearch, History, Settings, Cpu, AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../api/client'
import { useAppStore } from '../store/appStore'

const navItems = [
  { to: '/dashboard', label: 'Organize', icon: FolderSearch },
  { to: '/history', label: 'History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings }
]

const LLM_POLL_INTERVAL = 30_000 // 30 seconds

export default function Layout() {
  const { llmStatus, llmStatusDetail, setLLMStatus } = useAppStore()
  const [bannerDismissed, setBannerDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const res = await api.llmHealth()
        if (!cancelled) {
          setLLMStatus(res.ok ? 'ok' : 'error', res.detail)
          // Re-show the banner if health flips back to error after being dismissed
          if (!res.ok) setBannerDismissed(false)
        }
      } catch {
        if (!cancelled) {
          setLLMStatus('error', 'Could not reach the backend')
          setBannerDismissed(false)
        }
      }
    }

    check()
    const id = setInterval(check, LLM_POLL_INTERVAL)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [setLLMStatus])

  const showBanner = llmStatus === 'error' && !bannerDismissed

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      {/* Sidebar */}
      <aside className="w-56 flex-none bg-gray-900 border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-5 border-b border-gray-800">
          <Cpu className="h-6 w-6 text-brand-500" />
          <span className="text-lg font-semibold text-white tracking-tight">Caibinet</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 space-y-1 px-2">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-brand-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* LLM status indicator */}
        <div className="px-4 py-3 border-t border-gray-800 flex items-center gap-2">
          <span
            className={clsx(
              'h-2 w-2 rounded-full flex-none',
              llmStatus === 'ok' && 'bg-green-400',
              llmStatus === 'error' && 'bg-red-400 animate-pulse',
              llmStatus === 'unknown' && 'bg-gray-500'
            )}
          />
          <p className="text-xs text-gray-500 truncate">
            {llmStatus === 'ok' ? 'LLM connected' : llmStatus === 'error' ? 'LLM unavailable' : 'Checking LLM…'}
          </p>
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-gray-800">
          <p className="text-xs text-gray-600">v0.1.0 · Local AI</p>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* LLM warning banner */}
        {showBanner && (
          <div className="flex items-start gap-3 bg-amber-950 border-b border-amber-800 px-4 py-3 text-amber-300">
            <AlertTriangle className="h-4 w-4 flex-none mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">LLM is unavailable</p>
              <p className="text-xs text-amber-400 mt-0.5 break-words">{llmStatusDetail}</p>
              <p className="text-xs text-amber-500 mt-1">
                Scans will fail until the LLM is reachable. Check your{' '}
                <NavLink to="/settings" className="underline hover:text-amber-300">
                  Settings
                </NavLink>{' '}
                to verify the Ollama URL and model.
              </p>
            </div>
            <button
              onClick={() => setBannerDismissed(true)}
              className="flex-none text-amber-500 hover:text-amber-300 transition-colors"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
