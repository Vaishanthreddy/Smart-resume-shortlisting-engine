import { useCallback, useEffect, useState } from 'react'
import { CircleDot, FileWarning, RotateCcw } from 'lucide-react'
import type { Candidate, HealthResponse, RankResponse } from './types'
import { getHealth, rankResumes, readError } from './services/api'
import CandidateComparison from './components/CandidateComparison'
import CandidateDetails from './components/CandidateDetails'
import ErrorMessage from './components/ErrorMessage'
import FileUpload, { type FileRejection } from './components/FileUpload'
import JobAnalysis from './components/JobAnalysis'
import RankingTable from './components/RankingTable'
import TopCandidates from './components/TopCandidates'

export default function App() {
  const [jdFile, setJdFile] = useState<File | null>(null)
  const [resumeFiles, setResumeFiles] = useState<File[]>([])
  const [result, setResult] = useState<RankResponse | null>(null)
  const [isRanking, setIsRanking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rejections, setRejections] = useState<FileRejection[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [openCandidate, setOpenCandidate] = useState<Candidate | null>(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  const handleRejections = useCallback((items: FileRejection[]) => {
    if (items.length) setRejections(items)
  }, [])

  const runRanking = async () => {
    if (!jdFile || resumeFiles.length === 0) return
    setIsRanking(true)
    setError(null)
    setRejections([])
    setOpenCandidate(null)
    try {
      setResult(await rankResumes(jdFile, resumeFiles))
    } catch (caught) {
      setError(readError(caught))
      setResult(null)
    } finally {
      setIsRanking(false)
    }
  }

  const startOver = () => {
    setResult(null)
    setJdFile(null)
    setResumeFiles([])
    setError(null)
    setRejections([])
    setOpenCandidate(null)
  }

  const modelIsReady = health?.semantic_model_status === 'ready'

  return (
    <div className="min-h-screen">
      <header className="bg-paper border-b border-rule">
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-base font-semibold leading-tight">
              Smart Resume Shortlisting Engine
            </h1>
            <p className="text-micro text-muted">
              Relevance ranking with the evidence behind every score
            </p>
          </div>

          <div className="flex items-center gap-4">
            {health && (
              <p className="text-micro text-muted flex items-center gap-1.5">
                <CircleDot
                  className={`w-3 h-3 ${modelIsReady ? 'text-evidence' : 'text-gap'}`}
                  aria-hidden
                />
                {modelIsReady
                  ? `Embeddings: ${health.model_name}`
                  : `Embeddings: lexical fallback (${health.model_name} unavailable)`}
              </p>
            )}
            {result && (
              <button type="button" onClick={startOver} className="btn-quiet text-xs px-3 py-1.5">
                <RotateCcw className="w-3.5 h-3.5" aria-hidden />
                Start over
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
        {!result && (
          <>
            <FileUpload
              jdFile={jdFile}
              resumeFiles={resumeFiles}
              onJdChange={setJdFile}
              onResumesChange={setResumeFiles}
              onRank={runRanking}
              isRanking={isRanking}
              onRejections={handleRejections}
            />

            {!jdFile && resumeFiles.length === 0 && !isRanking && (
              <section className="panel p-6">
                <h2 className="text-sm font-semibold mb-3">How the ranking is produced</h2>
                <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                  {[
                    {
                      title: 'Read the job description',
                      body: 'Requirements, required and preferred skills, education, certifications and soft skills are extracted with deterministic rules.',
                    },
                    {
                      title: 'Match explicitly',
                      body: 'Every resume is searched for those skills using a canonical taxonomy with aliases and safe word boundaries.',
                    },
                    {
                      title: 'Match by meaning',
                      body: 'Each requirement statement is compared against resume passages using sentence embeddings and cosine similarity.',
                    },
                    {
                      title: 'Score and rank',
                      body: 'Seven transparent components are combined with weights this job actually calls for. No model assigns a score.',
                    },
                  ].map((step, index) => (
                    <li key={step.title} className="border-t-2 border-ink pt-2">
                      <p className="num text-micro text-muted">Step {index + 1}</p>
                      <h3 className="font-semibold mt-0.5">{step.title}</h3>
                      <p className="text-ink/80 mt-1 leading-relaxed">{step.body}</p>
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </>
        )}

        {rejections.length > 0 && (
          <ErrorMessage
            title="Some files were not added"
            message={rejections.map((item) => item.reason).join(' ')}
            onDismiss={() => setRejections([])}
          />
        )}

        {error && <ErrorMessage message={error} onDismiss={() => setError(null)} />}

        {result && (
          <>
            {result.model.note && (
              <div className="panel border-focus/40 bg-focus/5 p-3 text-sm">{result.model.note}</div>
            )}

            {result.summary.failed_files.length > 0 && (
              <section className="panel border-gap/50 bg-gap/5 p-4">
                <h2 className="text-sm font-semibold text-gap flex items-center gap-2">
                  <FileWarning className="w-4 h-4" aria-hidden />
                  {result.summary.failed_files.length} file
                  {result.summary.failed_files.length === 1 ? '' : 's'} could not be read
                </h2>
                <p className="text-micro text-muted mt-1">
                  The remaining {result.summary.successfully_processed} candidates were ranked
                  normally.
                </p>
                <ul className="mt-2 space-y-1 text-sm">
                  {result.summary.failed_files.map((file) => (
                    <li key={file.filename} className="text-ink/90">
                      {file.error}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="grid gap-6 lg:grid-cols-[minmax(300px,360px)_1fr] items-start">
              <div className="lg:sticky lg:top-6">
                <JobAnalysis job={result.job} scoring={result.scoring} />
              </div>

              <div className="space-y-6 min-w-0">
                <p className="text-micro text-muted">
                  {result.summary.successfully_processed} of {result.summary.total_candidates}{' '}
                  resumes ranked against {result.job.semantic_requirement_count} requirement
                  statements. This is a relevance ranking, not a hiring decision.
                </p>

                <TopCandidates candidates={result.candidates} onOpenDetails={setOpenCandidate} />

                <RankingTable candidates={result.candidates} onOpenDetails={setOpenCandidate} />

                {result.candidates.length > 1 && (
                  <CandidateComparison
                    resultId={result.result_id}
                    candidates={result.candidates}
                  />
                )}
              </div>
            </div>
          </>
        )}
      </main>

      <CandidateDetails
        candidate={openCandidate}
        scoring={result?.scoring ?? {
          base_weights: {},
          effective_weights: {},
          active_components: [],
          inactive_components: [],
          activation_reasons: {},
          component_labels: {},
        }}
        onClose={() => setOpenCandidate(null)}
      />

      <footer className="max-w-[1400px] mx-auto px-6 py-6 text-micro text-muted border-t border-rule mt-6">
        Candidate names are shown for identification only. Name, gender, age, address,
        nationality and similar attributes are never used in scoring or ranking.
      </footer>
    </div>
  )
}
