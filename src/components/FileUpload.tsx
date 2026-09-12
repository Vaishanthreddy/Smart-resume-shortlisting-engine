import { useCallback, useId, useRef, useState } from 'react'
import { FileText, Files, Loader2, Play, Trash2, Upload, X } from 'lucide-react'

const ACCEPTED = ['.pdf', '.docx', '.txt']
const MAX_MB = 10

export interface FileRejection {
  filename: string
  reason: string
}

function validate(file: File): string | null {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
  if (!ACCEPTED.includes(extension)) {
    return `${file.name} is not a PDF, DOCX or TXT file.`
  }
  if (file.size === 0) {
    return `${file.name} is empty.`
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    return `${file.name} is ${(file.size / 1024 / 1024).toFixed(1)} MB, over the ${MAX_MB} MB limit.`
  }
  return null
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

interface DropZoneProps {
  label: string
  hint: string
  multiple: boolean
  icon: React.ReactNode
  onFiles: (files: File[]) => void
  disabled?: boolean
}

function DropZone({ label, hint, multiple, icon, onFiles, disabled }: DropZoneProps) {
  const [isOver, setIsOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setIsOver(false)
      if (disabled) return
      onFiles(Array.from(event.dataTransfer.files))
    },
    [disabled, onFiles],
  )

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setIsOver(true)
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={handleDrop}
      className={`border border-dashed p-5 text-center transition-colors ${
        isOver ? 'border-focus bg-focus/5' : 'border-rule bg-paper'
      } ${disabled ? 'opacity-60' : ''}`}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple={multiple}
        accept={ACCEPTED.join(',')}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []))
          event.target.value = ''
        }}
      />
      <div className="flex justify-center text-muted mb-2" aria-hidden>
        {icon}
      </div>
      <label htmlFor={inputId} className="block text-sm font-semibold cursor-pointer">
        {label}
      </label>
      <p className="text-micro text-muted mt-1">{hint}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="btn-quiet mt-3 text-xs px-3 py-1.5"
      >
        <Upload className="w-3.5 h-3.5" aria-hidden />
        Choose {multiple ? 'files' : 'file'}
      </button>
    </div>
  )
}

interface Props {
  jdFile: File | null
  resumeFiles: File[]
  onJdChange: (file: File | null) => void
  onResumesChange: (files: File[]) => void
  onRank: () => void
  isRanking: boolean
  onRejections: (rejections: FileRejection[]) => void
}

export default function FileUpload({
  jdFile,
  resumeFiles,
  onJdChange,
  onResumesChange,
  onRank,
  isRanking,
  onRejections,
}: Props) {
  const acceptJd = useCallback(
    (files: File[]) => {
      const rejections: FileRejection[] = []
      const accepted: File[] = []
      files.slice(0, 1).forEach((file) => {
        const problem = validate(file)
        if (problem) rejections.push({ filename: file.name, reason: problem })
        else accepted.push(file)
      })
      onRejections(rejections)
      if (accepted[0]) onJdChange(accepted[0])
    },
    [onJdChange, onRejections],
  )

  const acceptResumes = useCallback(
    (files: File[]) => {
      const rejections: FileRejection[] = []
      const accepted: File[] = []
      const existing = new Set(resumeFiles.map((file) => `${file.name}:${file.size}`))

      files.forEach((file) => {
        const problem = validate(file)
        if (problem) {
          rejections.push({ filename: file.name, reason: problem })
          return
        }
        const key = `${file.name}:${file.size}`
        if (existing.has(key)) {
          rejections.push({ filename: file.name, reason: `${file.name} is already in the list.` })
          return
        }
        existing.add(key)
        accepted.push(file)
      })

      onRejections(rejections)
      if (accepted.length) onResumesChange([...resumeFiles, ...accepted])
    },
    [onRejections, onResumesChange, resumeFiles],
  )

  const canRank = Boolean(jdFile) && resumeFiles.length > 0 && !isRanking

  return (
    <section aria-labelledby="upload-heading" className="panel p-5">
      <h2 id="upload-heading" className="rule-heading">
        Upload the job description and the resumes
      </h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <DropZone
            label="Job description"
            hint="One file. PDF, DOCX or TXT, up to 10 MB."
            multiple={false}
            disabled={isRanking}
            icon={<FileText className="w-6 h-6" />}
            onFiles={acceptJd}
          />
          {jdFile && (
            <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-field border border-rule text-sm">
              <FileText className="w-4 h-4 text-muted shrink-0" aria-hidden />
              <span className="flex-1 truncate">{jdFile.name}</span>
              <span className="num text-micro text-muted">{formatSize(jdFile.size)}</span>
              <button
                type="button"
                onClick={() => onJdChange(null)}
                disabled={isRanking}
                aria-label={`Remove ${jdFile.name}`}
                className="text-muted hover:text-gap"
              >
                <X className="w-4 h-4" aria-hidden />
              </button>
            </div>
          )}
        </div>

        <div>
          <DropZone
            label="Resumes"
            hint="Select or drop as many as you need."
            multiple
            disabled={isRanking}
            icon={<Files className="w-6 h-6" />}
            onFiles={acceptResumes}
          />
          {resumeFiles.length > 0 && (
            <div className="mt-2 border border-rule">
              <div className="flex items-center justify-between px-3 py-1.5 bg-field border-b border-rule">
                <span className="text-micro text-muted">
                  {resumeFiles.length} resume{resumeFiles.length === 1 ? '' : 's'} selected
                </span>
                <button
                  type="button"
                  onClick={() => onResumesChange([])}
                  disabled={isRanking}
                  className="text-micro text-muted hover:text-gap inline-flex items-center gap-1"
                >
                  <Trash2 className="w-3 h-3" aria-hidden />
                  Remove all
                </button>
              </div>
              <ul className="max-h-48 overflow-y-auto divide-y divide-rule/60">
                {resumeFiles.map((file, index) => (
                  <li key={`${file.name}-${index}`} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                    <span className="flex-1 truncate">{file.name}</span>
                    <span className="num text-micro text-muted">{formatSize(file.size)}</span>
                    <button
                      type="button"
                      disabled={isRanking}
                      onClick={() => onResumesChange(resumeFiles.filter((_, i) => i !== index))}
                      aria-label={`Remove ${file.name}`}
                      className="text-muted hover:text-gap"
                    >
                      <X className="w-4 h-4" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-5 pt-4 border-t border-rule">
        <button type="button" className="btn-primary" disabled={!canRank} onClick={onRank}>
          {isRanking ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              Ranking candidates…
            </>
          ) : (
            <>
              <Play className="w-4 h-4" aria-hidden />
              Rank candidates
            </>
          )}
        </button>
        <p className="text-micro text-muted" aria-live="polite">
          {isRanking
            ? 'Parsing documents, matching requirements and scoring every candidate.'
            : !jdFile
              ? 'Add a job description to continue.'
              : resumeFiles.length === 0
                ? 'Add at least one resume to continue.'
                : `Ready: 1 job description and ${resumeFiles.length} resume${
                    resumeFiles.length === 1 ? '' : 's'
                  }.`}
        </p>
      </div>
    </section>
  )
}
