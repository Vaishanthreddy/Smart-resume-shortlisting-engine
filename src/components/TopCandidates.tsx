import { ArrowRight } from 'lucide-react'
import type { Candidate } from '../types'
import { ContributionBar } from './ScoreBreakdown'

interface Props {
  candidates: Candidate[]
  onOpenDetails: (candidate: Candidate) => void
}

/** The three strongest matches, each with the reasoning behind the placement. */
export default function TopCandidates({ candidates, onOpenDetails }: Props) {
  const top = candidates.slice(0, 3)
  if (!top.length) return null

  return (
    <section aria-labelledby="top-heading" className="panel p-5">
      <h2 id="top-heading" className="rule-heading">
        Why these three ranked highest
      </h2>

      <ol className="space-y-5">
        {top.map((candidate) => {
          const penaltyPoints = candidate.penalties.reduce((sum, item) => sum + item.points, 0)
          return (
            <li key={candidate.candidate_id} className="grid gap-3 sm:grid-cols-[auto_1fr]">
              <div className="flex sm:flex-col items-center sm:items-start gap-2 sm:gap-0 sm:w-16">
                <span className="num text-3xl font-semibold leading-none">
                  {candidate.rank}
                </span>
                <span className="text-micro text-muted">
                  {candidate.final_score.toFixed(1)} / 100
                </span>
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-semibold">
                    {candidate.candidate_name}
                    <span className="font-normal text-muted text-micro ml-2">
                      {candidate.filename}
                    </span>
                  </h3>
                  <button
                    type="button"
                    onClick={() => onOpenDetails(candidate)}
                    className="text-micro text-focus inline-flex items-center gap-1 hover:underline"
                  >
                    Full evidence
                    <ArrowRight className="w-3 h-3" aria-hidden />
                  </button>
                </div>

                <div className="mt-2">
                  <ContributionBar
                    contributions={candidate.weighted_contributions}
                    finalScore={candidate.final_score}
                    penaltyPoints={penaltyPoints}
                    height="md"
                    showLegend
                  />
                </div>

                <p className="text-sm text-ink/90 mt-3 leading-relaxed">
                  {candidate.explanation}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
