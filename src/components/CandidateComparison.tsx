import { useEffect, useState } from 'react'
import { Loader2, Scale } from 'lucide-react'
import type { Candidate, CompareResponse } from '../types'
import { COMPONENT_COLORS } from '../types'
import { compareCandidates, readError } from '../services/api'
import ErrorMessage from './ErrorMessage'

interface Props {
  resultId: string
  candidates: Candidate[]
}

function SkillColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4 className="text-micro font-semibold text-muted mb-1.5">{title}</h4>
      {items.length ? (
        <ul className="flex flex-wrap gap-1">
          {items.map((item) => (
            <li key={item} className="chip-found">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-micro text-muted">—</p>
      )}
    </div>
  )
}

export default function CandidateComparison({ resultId, candidates }: Props) {
  const [aId, setAId] = useState(candidates[0]?.candidate_id ?? '')
  const [bId, setBId] = useState(candidates[1]?.candidate_id ?? '')
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setResult(null)
    setAId(candidates[0]?.candidate_id ?? '')
    setBId(candidates[1]?.candidate_id ?? '')
  }, [resultId, candidates])

  const canCompare = aId && bId && aId !== bId && !isLoading

  const runComparison = async () => {
    setIsLoading(true)
    setError(null)
    try {
      setResult(await compareCandidates(resultId, aId, bId))
    } catch (caught) {
      setError(readError(caught))
      setResult(null)
    } finally {
      setIsLoading(false)
    }
  }

  const options = candidates.map((candidate) => (
    <option key={candidate.candidate_id} value={candidate.candidate_id}>
      #{candidate.rank} · {candidate.candidate_name} ({candidate.final_score.toFixed(1)})
    </option>
  ))

  return (
    <section aria-labelledby="compare-heading" className="panel p-5">
      <h2 id="compare-heading" className="rule-heading flex items-center gap-2">
        <Scale className="w-4 h-4 text-muted" aria-hidden />
        Compare two candidates
      </h2>

      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <label className="text-sm">
          <span className="block text-micro text-muted mb-1">First candidate</span>
          <select
            value={aId}
            onChange={(event) => setAId(event.target.value)}
            className="w-full border border-rule bg-paper px-2 py-1.5 text-sm focus:border-focus outline-none"
          >
            {options}
          </select>
        </label>

        <label className="text-sm">
          <span className="block text-micro text-muted mb-1">Second candidate</span>
          <select
            value={bId}
            onChange={(event) => setBId(event.target.value)}
            className="w-full border border-rule bg-paper px-2 py-1.5 text-sm focus:border-focus outline-none"
          >
            {options}
          </select>
        </label>

        <button type="button" className="btn-primary" disabled={!canCompare} onClick={runComparison}>
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              Comparing…
            </>
          ) : (
            'Compare'
          )}
        </button>
      </div>

      {aId === bId && (
        <p className="text-micro text-muted mt-2">Pick two different candidates to compare.</p>
      )}

      {error && (
        <div className="mt-4">
          <ErrorMessage message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {result && (
        <div className="mt-5 pt-4 border-t border-rule">
          <p className="text-sm leading-relaxed text-ink/90">{result.explanation}</p>

          <table className="w-full text-sm mt-4">
            <caption className="sr-only">Component score differences</caption>
            <thead>
              <tr className="text-micro text-muted border-b border-rule">
                <th scope="col" className="text-left font-medium py-1.5">Component</th>
                <th scope="col" className="text-right font-medium py-1.5">
                  {result.candidate_a_name}
                </th>
                <th scope="col" className="text-right font-medium py-1.5">
                  {result.candidate_b_name}
                </th>
                <th scope="col" className="text-right font-medium py-1.5">Weighted gap</th>
              </tr>
            </thead>
            <tbody>
              {result.component_differences
                .filter((item) => item.effective_weight > 0)
                .map((item) => (
                  <tr key={item.component} className="border-b border-rule/60">
                    <th scope="row" className="text-left font-normal py-1.5">
                      <span className="flex items-center gap-2">
                        <span
                          className="w-2 h-2 shrink-0"
                          style={{ backgroundColor: COMPONENT_COLORS[item.component] }}
                          aria-hidden
                        />
                        {item.label}
                      </span>
                    </th>
                    <td
                      className={`text-right num py-1.5 ${
                        item.difference > 0 ? 'font-semibold text-evidence' : ''
                      }`}
                    >
                      {item.candidate_a_score.toFixed(1)}
                    </td>
                    <td
                      className={`text-right num py-1.5 ${
                        item.difference < 0 ? 'font-semibold text-evidence' : ''
                      }`}
                    >
                      {item.candidate_b_score.toFixed(1)}
                    </td>
                    <td className="text-right num py-1.5 text-muted">
                      {item.weighted_difference > 0 ? '+' : ''}
                      {item.weighted_difference.toFixed(2)}
                    </td>
                  </tr>
                ))}
              <tr className="font-semibold">
                <th scope="row" className="text-left py-2">Final score</th>
                <td className="text-right num py-2">
                  {result.candidate_a_final_score.toFixed(1)}
                </td>
                <td className="text-right num py-2">
                  {result.candidate_b_final_score.toFixed(1)}
                </td>
                <td className="text-right num py-2">
                  {result.final_score_difference > 0 ? '+' : ''}
                  {result.final_score_difference.toFixed(1)}
                </td>
              </tr>
            </tbody>
          </table>

          <div className="grid gap-4 sm:grid-cols-2 mt-5">
            <SkillColumn
              title={`Required skills only ${result.candidate_a_name} evidenced`}
              items={result.only_a_required_skills}
            />
            <SkillColumn
              title={`Required skills only ${result.candidate_b_name} evidenced`}
              items={result.only_b_required_skills}
            />
            <SkillColumn
              title={`Other keywords only ${result.candidate_a_name} evidenced`}
              items={result.only_a_other_keywords}
            />
            <SkillColumn
              title={`Other keywords only ${result.candidate_b_name} evidenced`}
              items={result.only_b_other_keywords}
            />
          </div>

          {result.shared_required_skills.length > 0 && (
            <div className="mt-4">
              <SkillColumn
                title="Required skills both candidates evidenced"
                items={result.shared_required_skills}
              />
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 mt-5">
            {[
              { name: result.candidate_a_name, evidence: result.a_best_evidence, missing: result.a_requirements_not_found },
              { name: result.candidate_b_name, evidence: result.b_best_evidence, missing: result.b_requirements_not_found },
            ].map((side) => (
              <div key={side.name}>
                <h4 className="text-micro font-semibold text-muted mb-1.5">
                  Strongest evidence · {side.name}
                </h4>
                {side.evidence.length ? (
                  <ul className="space-y-1.5 text-sm">
                    {side.evidence.map((line, index) => (
                      <li key={index} className="pl-3 border-l-2 border-evidence text-ink/90">
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-micro text-muted">
                    No requirement reached the evidence threshold.
                  </p>
                )}
                {side.missing.length > 0 && (
                  <>
                    <p className="text-micro text-muted mt-2">
                      No evidence found in the submitted resume for:
                    </p>
                    <ul className="flex flex-wrap gap-1 mt-1">
                      {side.missing.map((name) => (
                        <li key={name} className="chip-gap">
                          {name}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
