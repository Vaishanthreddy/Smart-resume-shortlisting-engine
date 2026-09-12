import { COMPONENT_COLORS, COMPONENT_ORDER, SHORT_LABELS } from '../types'

interface BarProps {
  contributions: Record<string, number>
  finalScore: number
  penaltyPoints?: number
  height?: 'sm' | 'md'
  showLegend?: boolean
}

/**
 * The final score drawn as its weighted parts. Each segment is one component's
 * contribution in points, so the bar literally shows where the score came from.
 */
export function ContributionBar({
  contributions,
  finalScore,
  penaltyPoints = 0,
  height = 'sm',
  showLegend = false,
}: BarProps) {
  const segments = COMPONENT_ORDER.filter((key) => (contributions[key] ?? 0) > 0.05)
  const barHeight = height === 'sm' ? 'h-2' : 'h-3'

  return (
    <div>
      <div
        className={`w-full ${barHeight} bg-field border border-rule flex overflow-hidden`}
        role="img"
        aria-label={`Final score ${finalScore.toFixed(1)} of 100, composed of ${segments
          .map((key) => `${SHORT_LABELS[key]} ${(contributions[key] ?? 0).toFixed(1)} points`)
          .join(', ')}`}
      >
        {segments.map((key) => (
          <div
            key={key}
            style={{
              width: `${contributions[key]}%`,
              backgroundColor: COMPONENT_COLORS[key],
            }}
            title={`${SHORT_LABELS[key]}: ${contributions[key].toFixed(1)} points`}
          />
        ))}
        {penaltyPoints > 0 && (
          <div
            style={{ width: `${penaltyPoints}%` }}
            className="bg-gap/25 border-l border-gap"
            title={`Penalty: -${penaltyPoints.toFixed(1)} points`}
          />
        )}
      </div>

      {showLegend && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {segments.map((key) => (
            <li key={key} className="flex items-center gap-1.5 text-micro text-muted">
              <span
                className="w-2.5 h-2.5 shrink-0"
                style={{ backgroundColor: COMPONENT_COLORS[key] }}
                aria-hidden
              />
              {SHORT_LABELS[key]}
              <span className="num text-ink">{contributions[key].toFixed(1)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface TableProps {
  componentScores: Record<string, number>
  contributions: Record<string, number>
  effectiveWeights: Record<string, number>
  labels: Record<string, string>
  finalScore: number
  penaltyPoints?: number
}

/** The arithmetic behind one candidate's final score, line by line. */
export default function ScoreBreakdown({
  componentScores,
  contributions,
  effectiveWeights,
  labels,
  finalScore,
  penaltyPoints = 0,
}: TableProps) {
  const active = COMPONENT_ORDER.filter((key) => key in effectiveWeights)
  const subtotal = active.reduce((sum, key) => sum + (contributions[key] ?? 0), 0)

  return (
    <table className="w-full text-sm">
      <caption className="sr-only">How the final score was calculated</caption>
      <thead>
        <tr className="text-micro text-muted border-b border-rule">
          <th scope="col" className="text-left font-medium py-1.5">Component</th>
          <th scope="col" className="text-right font-medium py-1.5">Score</th>
          <th scope="col" className="text-right font-medium py-1.5">Weight</th>
          <th scope="col" className="text-right font-medium py-1.5">Points</th>
        </tr>
      </thead>
      <tbody>
        {active.map((key) => (
          <tr key={key} className="border-b border-rule/60">
            <th scope="row" className="text-left font-normal py-1.5">
              <span className="flex items-center gap-2">
                <span
                  className="w-2 h-2 shrink-0"
                  style={{ backgroundColor: COMPONENT_COLORS[key] }}
                  aria-hidden
                />
                {labels[key] ?? SHORT_LABELS[key]}
              </span>
            </th>
            <td className="text-right num py-1.5">{(componentScores[key] ?? 0).toFixed(1)}</td>
            <td className="text-right num py-1.5 text-muted">
              {((effectiveWeights[key] ?? 0) * 100).toFixed(1)}%
            </td>
            <td className="text-right num py-1.5">{(contributions[key] ?? 0).toFixed(2)}</td>
          </tr>
        ))}
        {penaltyPoints > 0 && (
          <tr className="border-b border-rule/60 text-gap">
            <th scope="row" className="text-left font-normal py-1.5">
              Mandatory-skill penalty
            </th>
            <td colSpan={2} className="text-right num py-1.5 text-muted">
              subtotal {subtotal.toFixed(2)}
            </td>
            <td className="text-right num py-1.5">−{penaltyPoints.toFixed(2)}</td>
          </tr>
        )}
        <tr className="font-semibold">
          <th scope="row" className="text-left py-2">Final score</th>
          <td colSpan={2} />
          <td className="text-right num py-2">{finalScore.toFixed(2)}</td>
        </tr>
      </tbody>
    </table>
  )
}
