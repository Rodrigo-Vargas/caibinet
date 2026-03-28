import { Check, Loader2, Clock } from 'lucide-react'
import clsx from 'clsx'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type StepState = 'pending' | 'active' | 'done'

interface ScanPhaseStepperProps {
  /** Whether the scan worker is still running */
  isRunning: boolean
  /** Current phase value from the session ('summarizing' | 'analyzing' | 'deciding' | null) */
  phase: string | null | undefined
  /** Total files in the scan */
  totalFiles: number
  /** How many files have been processed in the current phase */
  processedFiles: number
  /** True if scan ended via cancellation */
  isCancelled?: boolean
  /** Live elapsed seconds (whole-process clock, including this phase) */
  elapsed?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatElapsed(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`
  const m = Math.floor(s / 60)
  const rem = Math.floor(s % 60)
  return `${m}m ${rem}s`
}

function stepNode(state: StepState, index: number) {
  if (state === 'done') {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-green-600 shrink-0">
        <Check className="h-4 w-4 text-white" strokeWidth={2.5} />
      </span>
    )
  }
  if (state === 'active') {
    return (
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 shrink-0">
        <Loader2 className="h-4 w-4 text-white animate-spin" />
      </span>
    )
  }
  // pending
  return (
    <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-gray-700 shrink-0">
      <span className="text-xs font-bold text-gray-600">{index}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ScanPhaseStepper({
  isRunning,
  phase,
  totalFiles,
  processedFiles,
  isCancelled = false,
  elapsed,
}: ScanPhaseStepperProps) {
  const isSummarizing = isRunning && phase === 'summarizing'
  const isAnalyzing = isRunning && phase === 'analyzing'
  const isDeciding = isRunning && phase === 'deciding'

  // Step 1 is done once we've moved past summarizing
  const step1Done = phase === 'analyzing' || phase === 'deciding' || (!isRunning && !isSummarizing)
  const step1Active = isSummarizing

  // Step 2 (analyzing) is done once we've moved past it
  const step2Done = phase === 'deciding' || (!isRunning && (step1Done && !isCancelled))
  const step2Active = isAnalyzing

  // Step 3 is done when the scan finished without cancellation
  const step3Done = !isRunning && step2Done && !isCancelled
  const step3Active = isDeciding

  const step1State: StepState = step1Done ? 'done' : step1Active ? 'active' : 'pending'
  const step2State: StepState = step2Done ? 'done' : step2Active ? 'active' : 'pending'
  const step3State: StepState = step3Done ? 'done' : step3Active ? 'active' : 'pending'

  const progressPct = totalFiles > 0 ? Math.round((processedFiles / totalFiles) * 100) : 0

  return (
    <div className="card py-3 px-4">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Progress</span>
        {elapsed != null && (
          <span className="flex items-center gap-1 text-xs text-gray-400" title="Elapsed time (full process)">
            <Clock className="h-3 w-3" />
            {formatElapsed(elapsed)}
          </span>
        )}
      </div>
      <div className="flex items-start gap-0">
        {/* ── Step 1: Analyze contents ── */}
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex items-center gap-2.5">
            {stepNode(step1State, 1)}
            <div className="min-w-0">
              <p
                className={clsx(
                  'text-sm font-medium leading-tight',
                  step1State === 'done'
                    ? 'text-green-400'
                    : step1State === 'active'
                      ? 'text-brand-300'
                      : 'text-gray-600'
                )}
              >
                Analyze contents
              </p>
              <p className="text-xs text-gray-500 mt-0.5 leading-tight">
                {step1State === 'done'
                  ? `${totalFiles} file${totalFiles !== 1 ? 's' : ''} summarized`
                  : step1State === 'active'
                    ? `${processedFiles} of ${totalFiles} files`
                    : 'Pending'}
              </p>
            </div>
          </div>

          {/* Inline progress bar — only visible while step 1 is active */}
          {step1State === 'active' && (
            <div className="ml-9 h-1.5 w-full max-w-[180px] rounded-full bg-gray-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-brand-500 transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          )}
        </div>

        {/* ── Connector 1→2 ── */}
        <div className="flex flex-col items-center mt-3.5 mx-2">
          <div
            className={clsx(
              'h-px w-8 transition-colors duration-500',
              step1State === 'done' ? 'bg-green-700' : 'bg-gray-700'
            )}
          />
        </div>

        {/* ── Step 2: Understand folder ── */}
        <div className="flex flex-1 flex-col gap-1">
          <div className="flex items-center gap-2.5">
            {stepNode(step2State, 2)}
            <div className="min-w-0">
              <p
                className={clsx(
                  'text-sm font-medium leading-tight',
                  step2State === 'done'
                    ? 'text-green-400'
                    : step2State === 'active'
                      ? 'text-brand-300'
                      : 'text-gray-600'
                )}
              >
                Understand folder
              </p>
              <p className="text-xs text-gray-500 mt-0.5 leading-tight">
                {step2State === 'done'
                  ? 'Role & groups found'
                  : step2State === 'active'
                    ? 'Analyzing structure…'
                    : 'Waiting for step 1'}
              </p>
            </div>
          </div>
        </div>

        {/* ── Connector 2→3 ── */}
        <div className="flex flex-col items-center mt-3.5 mx-2">
          <div
            className={clsx(
              'h-px w-8 transition-colors duration-500',
              step2State === 'done' ? 'bg-green-700' : 'bg-gray-700'
            )}
          />
        </div>

        {/* ── Step 3: Review & organize ── */}
        <div className="flex flex-1 flex-col gap-1">
          <div className="flex items-center gap-2.5">
            {stepNode(step3State, 3)}
            <div className="min-w-0">
              <p
                className={clsx(
                  'text-sm font-medium leading-tight',
                  step3State === 'done'
                    ? 'text-green-400'
                    : step3State === 'active'
                      ? 'text-brand-300'
                      : 'text-gray-600'
                )}
              >
                Review &amp; organize
              </p>
              <p className="text-xs text-gray-500 mt-0.5 leading-tight">
                {step3State === 'done'
                  ? `${totalFiles} file${totalFiles !== 1 ? 's' : ''} reviewed`
                  : step3State === 'active'
                    ? `${processedFiles} of ${totalFiles} files`
                    : isCancelled && step1State === 'done'
                      ? 'Stopped'
                      : 'Waiting for step 2'}
              </p>
            </div>
          </div>
        </div>

        {/* ── Cancelled notice ── */}
        {isCancelled && (
          <div className="ml-4 flex items-center self-center gap-1 text-xs text-gray-500 shrink-0">
            Stopped
          </div>
        )}
      </div>
    </div>
  )
}
