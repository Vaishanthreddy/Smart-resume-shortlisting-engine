import { useEffect, useRef } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import type { Candidate, MatchedItem, ScoringInfo, SemanticEvidence } from '../types'
import ScoreBreakdown from './ScoreBreakdown'

interface Props {
  candidate: Candidate | null
  scoring: ScoringInfo
  onClose: () => void
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="py-4 border-b border-rule/60 last:border-0">
      <h3 className="text-micro font-semibold text-muted mb-2">{title}</h3>
      {children}
    </section>
  )
}

function EvidencePairs({ items, emptyNote }: { items: SemanticEvidence[]; emptyNote: string }) {
  if (!items.length) return <p className="text-micro text-muted">{emptyNote}</p>
  return (
    <ul className="space-y-3">
      {items.map((item, index) => (
        <li key={index} className="text-sm">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-ink/80">{item.requirement}</p>
            <span
              className={`num text-micro shrink-0 ${
                item.meets_threshold ? 'text-evidence' : 'text-muted'
              }`}
            >
              {item.similarity.toFixed(2)}
            </span>
          </div>
          <p
            className={`mt-1 pl-3 border-l-2 ${
              item.meets_threshold ? 'border-evidence' : 'border-rule'
            } text-ink/90`}
          >
            {item.best_evidence || 'No supporting passage was found in the submitted resume.'}
          </p>
          <p className="text-micro text-muted mt-0.5">
            {item.requirement_type} requirement ·{' '}
            {item.meets_threshold ? 'meets the evidence threshold' : 'below the evidence threshold'}
          </p>
        </li>
      ))}
    </ul>
  )
}

function MatchedList({ items, emptyNote }: { items: MatchedItem[]; emptyNote: string }) {
  if (!items.length) return <p className="text-micro text-muted">{emptyNote}</p>
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.name} className="text-sm">
          <div className="flex items-baseline gap-2">
            <span className="font-medium">{item.name}</span>
            <span className="text-micro text-muted">
              {item.match_method}
              {item.found_in ? ` · found in ${item.found_in}` : ''}
            </span>
          </div>
          {item.evidence && (
            <p className="text-ink/80 pl-3 border-l-2 border-evidence/50 mt-0.5">
              {item.evidence}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function NotFoundList({ items }: { items: string[] }) {
  if (!items.length) return null
  return (
    <ul className="flex flex-wrap gap-1.5 mt-2">
      {items.map((name) => (
        <li key={name} className="chip-gap">
          {name}
        </li>
      ))}
    </ul>
  )
}

export default function CandidateDetails({ candidate, scoring, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!candidate) return
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [candidate, onClose])

  if (!candidate) return null

  const penaltyPoints = candidate.penalties.reduce((sum, item) => sum + item.points, 0)

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-ink/30"
        onClick={onClose}
        role="presentation"
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-heading"
        className="relative bg-paper w-full max-w-2xl h-full overflow-y-auto border-l border-rule"
      >
        <header className="sticky top-0 bg-paper border-b border-rule px-6 py-4 flex items-start justify-between gap-4 z-10">
          <div className="min-w-0">
            <p className="text-micro text-muted">
              Rank <span className="num">{candidate.rank}</span> · {candidate.candidate_id}
            </p>
            <h2 id="detail-heading" className="text-lg font-semibold truncate">
              {candidate.candidate_name}
            </h2>
            <p className="text-micro text-muted truncate">{candidate.filename}</p>
          </div>
          <div className="flex items-start gap-3">
            <div className="text-right">
              <p className="num text-2xl font-semibold leading-none">
                {candidate.final_score.toFixed(1)}
              </p>
              <p className="text-micro text-muted">of 100</p>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close candidate details"
              className="text-muted hover:text-ink"
            >
              <X className="w-5 h-5" aria-hidden />
            </button>
          </div>
        </header>

        <div className="px-6 pb-10">
          <Block title="How this final score was calculated">
            <ScoreBreakdown
              componentScores={candidate.component_scores}
              contributions={candidate.weighted_contributions}
              effectiveWeights={scoring.effective_weights}
              labels={scoring.component_labels}
              finalScore={candidate.final_score}
              penaltyPoints={penaltyPoints}
            />
            <p className="text-micro text-muted mt-2">
              Weights are the effective weights for this job description and are identical for
              every candidate.
            </p>
          </Block>

          <Block title="Explanation">
            <p className="text-sm leading-relaxed text-ink/90">{candidate.explanation}</p>
          </Block>

          {candidate.penalties.length > 0 && (
            <Block title="Penalties applied">
              <ul className="space-y-2">
                {candidate.penalties.map((penalty, index) => (
                  <li key={index} className="flex gap-2 text-sm">
                    <AlertTriangle className="w-4 h-4 text-gap shrink-0 mt-0.5" aria-hidden />
                    <div>
                      <p className="font-medium text-gap">
                        −{penalty.points.toFixed(1)} points · {penalty.reason}
                      </p>
                      <p className="text-ink/80">{penalty.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Block>
          )}

          <Block title="Required skills matched">
            <MatchedList
              items={candidate.matched_required_skills}
              emptyNote="No required skill was matched in the submitted resume."
            />
            {candidate.required_skills_not_found.length > 0 && (
              <>
                <p className="text-micro text-muted mt-3">
                  No evidence of the following was found in the submitted resume:
                </p>
                <NotFoundList items={candidate.required_skills_not_found} />
              </>
            )}
          </Block>

          <Block title="Other keywords matched">
            <MatchedList
              items={candidate.matched_other_keywords}
              emptyNote="None of the preferred or domain keywords were found."
            />
            {candidate.other_keywords_not_found.length > 0 && (
              <>
                <p className="text-micro text-muted mt-3">Not found:</p>
                <NotFoundList items={candidate.other_keywords_not_found} />
              </>
            )}
          </Block>

          <Block title="Requirement-to-evidence matches">
            <EvidencePairs
              items={candidate.semantic_evidence}
              emptyNote="No requirement statements were available to match."
            />
          </Block>

          <Block title="Project and experience evidence">
            <EvidencePairs
              items={candidate.project_experience_evidence}
              emptyNote="No project or employment passage reached the evidence threshold."
            />
          </Block>

          {(candidate.education_evidence.length > 0 ||
            candidate.education_not_found.length > 0) && (
            <Block title="Education">
              <MatchedList
                items={candidate.education_evidence}
                emptyNote="No evidence of the requested education was found in the submitted resume."
              />
              <NotFoundList items={candidate.education_not_found} />
            </Block>
          )}

          {(candidate.certification_evidence.length > 0 ||
            candidate.certifications_not_found.length > 0) && (
            <Block title="Certifications">
              <MatchedList
                items={candidate.certification_evidence}
                emptyNote="No evidence of the requested certifications was found in the submitted resume."
              />
              <NotFoundList items={candidate.certifications_not_found} />
            </Block>
          )}

          {(candidate.soft_skill_evidence.length > 0 ||
            candidate.soft_skills_not_found.length > 0) && (
            <Block title="Soft-skill evidence">
              <MatchedList
                items={candidate.soft_skill_evidence}
                emptyNote="No supporting behavioural evidence was found in the submitted resume."
              />
              <NotFoundList items={candidate.soft_skills_not_found} />
              <p className="text-micro text-muted mt-2">
                Soft skills carry the lowest weight and are only credited when a sentence in the
                resume supports them.
              </p>
            </Block>
          )}

          {candidate.whole_document_similarity !== null && (
            <Block title="Diagnostics">
              <p className="text-sm">
                Whole-document similarity:{' '}
                <span className="num">{candidate.whole_document_similarity.toFixed(3)}</span>
              </p>
              <p className="text-micro text-muted mt-1">
                Reported for reference only. It carries no weight in the final score, which is
                built from requirement-level comparisons.
              </p>
            </Block>
          )}

          {candidate.warnings.length > 0 && (
            <Block title="Document notes">
              <ul className="space-y-1 text-micro text-muted">
                {candidate.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </Block>
          )}
        </div>
      </div>
    </div>
  )
}
