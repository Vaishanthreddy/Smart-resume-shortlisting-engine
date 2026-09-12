import { useState } from 'react'
import { ChevronDown, Info, ScanSearch } from 'lucide-react'
import type { JobAnalysis as JobAnalysisType, ScoringInfo } from '../types'
import { COMPONENT_COLORS, COMPONENT_ORDER, SHORT_LABELS } from '../types'

interface Props {
  job: JobAnalysisType
  scoring: ScoringInfo
}

function ChipList({ items, variant }: { items: string[]; variant: 'found' | 'neutral' }) {
  if (!items.length) return <p className="text-micro text-muted">None detected.</p>
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className={variant === 'found' ? 'chip-found' : 'chip-neutral'}>
          {item}
        </li>
      ))}
    </ul>
  )
}

function Section({
  title,
  count,
  children,
}: {
  title: string
  count?: number
  children: React.ReactNode
}) {
  return (
    <div className="py-3 border-b border-rule/60 last:border-0">
      <h3 className="text-micro font-semibold text-muted mb-2">
        {title}
        {count !== undefined && <span className="num ml-1.5 text-ink">{count}</span>}
      </h3>
      {children}
    </div>
  )
}

export default function JobAnalysis({ job, scoring }: Props) {
  const [showAllResponsibilities, setShowAllResponsibilities] = useState(false)
  const responsibilities = showAllResponsibilities
    ? job.responsibilities
    : job.responsibilities.slice(0, 5)

  return (
    <section aria-labelledby="jd-heading" className="panel p-5">
      <h2 id="jd-heading" className="rule-heading flex items-center gap-2">
        <ScanSearch className="w-4 h-4 text-muted" aria-hidden />
        What the job description asks for
      </h2>

      <p className="text-lg font-semibold leading-snug">{job.title}</p>
      {job.experience_expectation && (
        <p className="text-sm text-muted mt-0.5">
          Experience expectation: {job.experience_expectation}
        </p>
      )}

      <Section title="Required skills" count={job.required_skills.length}>
        <ChipList items={job.required_skills} variant="found" />
      </Section>

      <Section title="Preferred and other keywords" count={job.other_keywords.length}>
        <ChipList items={job.other_keywords} variant="neutral" />
      </Section>

      {job.responsibilities.length > 0 && (
        <Section title="Responsibilities" count={job.responsibilities.length}>
          <ul className="space-y-1.5 text-sm">
            {responsibilities.map((item, index) => (
              <li key={index} className="pl-3 border-l-2 border-rule text-ink/90">
                {item}
              </li>
            ))}
          </ul>
          {job.responsibilities.length > 5 && (
            <button
              type="button"
              onClick={() => setShowAllResponsibilities((value) => !value)}
              className="text-micro text-focus mt-2 inline-flex items-center gap-1"
            >
              <ChevronDown
                className={`w-3 h-3 transition-transform ${showAllResponsibilities ? 'rotate-180' : ''}`}
                aria-hidden
              />
              {showAllResponsibilities
                ? 'Show fewer'
                : `Show all ${job.responsibilities.length}`}
            </button>
          )}
        </Section>
      )}

      {job.education_requirements.length > 0 && (
        <Section title="Education">
          <ChipList items={job.education_requirements} variant="neutral" />
        </Section>
      )}

      {job.certification_requirements.length > 0 && (
        <Section title="Certifications">
          <ChipList items={job.certification_requirements} variant="neutral" />
        </Section>
      )}

      {job.soft_skills.length > 0 && (
        <Section title="Soft skills requested">
          <ChipList items={job.soft_skills} variant="neutral" />
        </Section>
      )}

      <Section title="Scoring weights applied to every candidate">
        <ul className="space-y-1.5">
          {COMPONENT_ORDER.map((key) => {
            const weight = scoring.effective_weights[key]
            const isActive = weight !== undefined
            const base = scoring.base_weights[key] ?? 0
            return (
              <li key={key} className="text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <span className={isActive ? 'text-ink' : 'text-muted line-through'}>
                    {SHORT_LABELS[key]}
                  </span>
                  <span className={`num text-micro ${isActive ? 'text-ink' : 'text-muted'}`}>
                    {isActive ? `${(weight * 100).toFixed(1)}%` : 'inactive'}
                    {isActive && Math.abs(weight - base) > 0.0005 && (
                      <span className="text-muted"> (base {(base * 100).toFixed(0)}%)</span>
                    )}
                  </span>
                </div>
                {isActive && (
                  <div className="h-1 bg-field mt-1">
                    <div
                      className="h-full"
                      style={{
                        width: `${weight * 100}%`,
                        backgroundColor: COMPONENT_COLORS[key],
                      }}
                    />
                  </div>
                )}
              </li>
            )
          })}
        </ul>

        {scoring.inactive_components.length > 0 && (
          <p className="text-micro text-muted mt-3 leading-relaxed">
            {scoring.inactive_components.map((key) => SHORT_LABELS[key]).join(', ')}{' '}
            {scoring.inactive_components.length === 1 ? 'is' : 'are'} inactive for this job, so
            that weight is shared proportionally across the active components. No candidate
            loses points for a category this job description never asked about.
          </p>
        )}
      </Section>

      {job.analysis_notes.length > 0 && (
        <Section title="Notes on this analysis">
          <ul className="space-y-1 text-micro text-muted">
            {job.analysis_notes.map((note, index) => (
              <li key={index} className="flex gap-1.5">
                <Info className="w-3 h-3 shrink-0 mt-0.5" aria-hidden />
                {note}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {job.bias_flags.length > 0 && (
        <Section title="Wording to review" count={job.bias_flags.length}>
          <p className="text-micro text-muted mb-2">
            Suggestions about the job description for a person to review. These never affect any
            candidate&apos;s score.
          </p>
          <ul className="space-y-2">
            {job.bias_flags.map((flag, index) => (
              <li key={index} className="border-l-2 border-gap pl-3 py-0.5">
                <p className="text-micro font-semibold text-gap">{flag.category}</p>
                <p className="text-sm text-ink/90">{flag.message}</p>
                {flag.evidence && (
                  <p className="text-micro text-muted mt-0.5 italic">“{flag.evidence}”</p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </section>
  )
}
