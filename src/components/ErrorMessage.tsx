import { AlertTriangle, X } from 'lucide-react'

interface Props {
  message: string
  title?: string
  onDismiss?: () => void
}

/** Says what went wrong and what to do about it. */
export default function ErrorMessage({ message, title = 'That did not work', onDismiss }: Props) {
  return (
    <div role="alert" className="panel border-gap/50 bg-gap/5 p-4 flex gap-3">
      <AlertTriangle className="w-5 h-5 text-gap shrink-0 mt-0.5" aria-hidden />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gap">{title}</p>
        <p className="text-sm text-ink mt-1 break-words">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss this message"
          className="text-muted hover:text-ink shrink-0"
        >
          <X className="w-4 h-4" aria-hidden />
        </button>
      )}
    </div>
  )
}
