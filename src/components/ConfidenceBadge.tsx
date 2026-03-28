import clsx from 'clsx'

interface ConfidenceBadgeProps {
  value: number // 0.0 – 1.0
}

export default function ConfidenceBadge({ value }: ConfidenceBadgeProps) {
  const pct = Math.round(value * 100)

  const cls =
    value >= 0.75
      ? 'badge-green'
      : value >= 0.5
        ? 'badge-yellow'
        : 'badge-red'

  return (
    <span className={clsx('badge font-mono tabular-nums', cls)}>
      {pct}%
    </span>
  )
}
