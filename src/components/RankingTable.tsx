import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Search } from 'lucide-react'
import type { Candidate } from '../types'
import { ContributionBar } from './ScoreBreakdown'

type SortKey =
  | 'rank'
  | 'final_score'
  | 'required_skills'
  | 'semantic_match'
  | 'other_keywords'
  | 'project_experience'

interface Props {
  candidates: Candidate[]
  onOpenDetails: (candidate: Candidate) => void
}

const COLUMNS: { key: SortKey; label: string; short: string }[] = [
  { key: 'final_score', label: 'Final score', short: 'Final' },
  { key: 'required_skills', label: 'Required-skill score', short: 'Required' },
  { key: 'semantic_match', label: 'Semantic score', short: 'Semantic' },
  { key: 'other_keywords', label: 'Other keyword score', short: 'Keywords' },
  { key: 'project_experience', label: 'Project and experience score', short: 'Projects' },
]

function valueFor(candidate: Candidate, key: SortKey): number {
  if (key === 'rank') return candidate.rank
  if (key === 'final_score') return candidate.final_score
  return candidate.component_scores[key] ?? 0
}

export default function RankingTable({ candidates, onOpenDetails }: Props) {
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('rank')
  const [ascending, setAscending] = useState(true)

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const filtered = needle
      ? candidates.filter(
          (candidate) =>
            candidate.candidate_name.toLowerCase().includes(needle) ||
            candidate.filename.toLowerCase().includes(needle) ||
            candidate.matched_required_skills.some((item) =>
              item.name.toLowerCase().includes(needle),
            ),
        )
      : candidates

    return [...filtered].sort((a, b) => {
      const difference = valueFor(a, sortKey) - valueFor(b, sortKey)
      return ascending ? difference : -difference
    })
  }, [ascending, candidates, query, sortKey])

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setAscending((value) => !value)
    } else {
      setSortKey(key)
      setAscending(key === 'rank')
    }
  }

  const SortIcon = ascending ? ArrowUp : ArrowDown

  return (
    <section aria-labelledby="ranking-heading" className="panel">
      <div className="flex flex-wrap items-center justify-between gap-3 p-5 pb-3">
        <h2 id="ranking-heading" className="text-sm font-semibold">
          Every candidate, ranked
          <span className="num text-muted font-normal ml-2">{candidates.length}</span>
        </h2>
        <div className="relative">
          <Search
            className="w-4 h-4 text-muted absolute left-2.5 top-1/2 -translate-y-1/2"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, file or skill"
            aria-label="Search candidates"
            className="pl-8 pr-3 py-1.5 text-sm border border-rule bg-paper w-64 max-w-full focus:border-focus outline-none"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-t border-rule">
          <caption className="sr-only">
            Candidates ranked by relevance to the job description
          </caption>
          <thead>
            <tr className="bg-field text-micro text-muted">
              <th scope="col" className="text-left font-medium px-3 py-2 w-12">
                <button type="button" onClick={() => toggleSort('rank')} className="hover:text-ink">
                  Rank {sortKey === 'rank' && <SortIcon className="w-3 h-3 inline" aria-hidden />}
                </button>
              </th>
              <th scope="col" className="text-left font-medium px-3 py-2 min-w-[180px]">
                Candidate
              </th>
              {COLUMNS.map((column) => (
                <th key={column.key} scope="col" className="text-right font-medium px-3 py-2">
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    title={`Sort by ${column.label}`}
                    className="hover:text-ink whitespace-nowrap"
                  >
                    {column.short}{' '}
                    {sortKey === column.key && <SortIcon className="w-3 h-3 inline" aria-hidden />}
                  </button>
                </th>
              ))}
              <th scope="col" className="text-left font-medium px-3 py-2 min-w-[220px]">
                Main matches
              </th>
              <th scope="col" className="text-left font-medium px-3 py-2 min-w-[180px]">
                Not found
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule/70">
            {rows.map((candidate) => {
              const isTopThree = candidate.rank <= 3
              const penaltyPoints = candidate.penalties.reduce(
                (sum, item) => sum + item.points,
                0,
              )
              return (
                <tr
                  key={candidate.candidate_id}
                  className={isTopThree ? 'bg-evidence/[0.04]' : undefined}
                >
                  <td className="px-3 py-2.5 align-top">
                    <span
                      className={`num ${isTopThree ? 'font-semibold text-evidence' : 'text-muted'}`}
                    >
                      {candidate.rank}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <div className="font-medium leading-tight">{candidate.candidate_name}</div>
                    <div className="text-micro text-muted truncate max-w-[220px]">
                      {candidate.filename}
                    </div>
                    <div className="mt-1.5 w-32">
                      <ContributionBar
                        contributions={candidate.weighted_contributions}
                        finalScore={candidate.final_score}
                        penaltyPoints={penaltyPoints}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right align-top num font-semibold">
                    {candidate.final_score.toFixed(1)}
                  </td>
                  {COLUMNS.slice(1).map((column) => (
                    <td key={column.key} className="px-3 py-2.5 text-right align-top num text-muted">
                      {(candidate.component_scores[column.key] ?? 0).toFixed(1)}
                    </td>
                  ))}
                  <td className="px-3 py-2.5 align-top">
                    <ul className="flex flex-wrap gap-1">
                      {candidate.matched_required_skills.slice(0, 4).map((item) => (
                        <li key={item.name} className="chip-found">
                          {item.name}
                        </li>
                      ))}
                      {candidate.matched_required_skills.length > 4 && (
                        <li className="chip-neutral">
                          +{candidate.matched_required_skills.length - 4}
                        </li>
                      )}
                      {candidate.matched_required_skills.length === 0 && (
                        <li className="text-micro text-muted">No required skills matched</li>
                      )}
                    </ul>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <ul className="flex flex-wrap gap-1">
                      {candidate.required_skills_not_found.slice(0, 3).map((name) => (
                        <li key={name} className="chip-gap">
                          {name}
                        </li>
                      ))}
                      {candidate.required_skills_not_found.length > 3 && (
                        <li className="chip-neutral">
                          +{candidate.required_skills_not_found.length - 3}
                        </li>
                      )}
                      {candidate.required_skills_not_found.length === 0 && (
                        <li className="text-micro text-muted">—</li>
                      )}
                    </ul>
                  </td>
                  <td className="px-3 py-2.5 align-top text-right">
                    <button
                      type="button"
                      onClick={() => onOpenDetails(candidate)}
                      className="btn-quiet text-xs px-2.5 py-1"
                    >
                      Details
                    </button>
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-sm text-muted">
                  No candidate matches “{query}”. Clear the search to see everyone.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
