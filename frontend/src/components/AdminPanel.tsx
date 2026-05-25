import { useState, useCallback, useRef } from 'react'
import { getAuthHeaders } from './AuthGuard'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024 // 200 MB

type JobStatus = 'pending' | 'running' | 'completed' | 'failed'

interface RetrainJob {
  job_id: string
  status: JobStatus
  message?: string
}

// ── Spinner icon ──────────────────────────────────────────────────────────────
function Spinner({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg
      className={`${className} animate-spin`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}

// ── Error icon ────────────────────────────────────────────────────────────────
function ErrorIcon() {
  return (
    <svg
      className="w-4 h-4 flex-shrink-0"
      fill="currentColor"
      viewBox="0 0 20 20"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  )
}

// ── Job status badge ──────────────────────────────────────────────────────────
function JobStatusBadge({ status }: { status: JobStatus }) {
  const styles: Record<JobStatus, string> = {
    pending:
      'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700',
    running:
      'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300 border-blue-300 dark:border-blue-700',
    completed:
      'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-300 dark:border-green-700',
    failed:
      'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-300 dark:border-red-700',
  }

  const icons: Record<JobStatus, React.ReactNode> = {
    pending: <span aria-hidden="true">⏳</span>,
    running: <Spinner className="w-3.5 h-3.5" />,
    completed: <span aria-hidden="true">✅</span>,
    failed: <span aria-hidden="true">❌</span>,
  }

  const labels: Record<JobStatus, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold border ${styles[status]}`}
      role="status"
      aria-label={`Job status: ${labels[status]}`}
    >
      {icons[status]}
      {labels[status]}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export function AdminPanel() {
  // CSV upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const [uploadServerError, setUploadServerError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Retrain state
  const [retrainLoading, setRetrainLoading] = useState(false)
  const [retrainError, setRetrainError] = useState<string | null>(null)
  const [currentJob, setCurrentJob] = useState<RetrainJob | null>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── File selection ──────────────────────────────────────────────────────────
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setFileError(null)
    setUploadServerError(null)
    setUploadSuccess(false)

    const file = e.target.files?.[0] ?? null
    if (!file) {
      setSelectedFile(null)
      return
    }

    // Client-side validation: CSV extension
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setFileError('Only CSV files are accepted. Please select a file with a .csv extension.')
      setSelectedFile(null)
      // Reset the input so the same file can be re-selected after fixing
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    // Client-side validation: ≤ 200 MB
    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1)
      setFileError(
        `File is too large (${sizeMB} MB). Maximum allowed size is 200 MB.`,
      )
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    setSelectedFile(file)
  }, [])

  // ── CSV upload ──────────────────────────────────────────────────────────────
  const handleUpload = useCallback(async () => {
    if (!selectedFile) return

    setUploadServerError(null)
    setUploadSuccess(false)
    setUploadLoading(true)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch(`${API_BASE_URL}/api/v1/admin/dataset`, {
        method: 'POST',
        headers: { ...getAuthHeaders() },
        body: formData,
      })

      if (!response.ok) {
        let message = `Upload failed (HTTP ${response.status}).`
        try {
          const data = await response.json()
          if (data?.detail) {
            message =
              typeof data.detail === 'string'
                ? data.detail
                : JSON.stringify(data.detail)
          } else if (data?.message) {
            message = String(data.message)
          }
        } catch {
          // ignore JSON parse errors
        }

        if (response.status === 413) {
          message = 'File exceeds the server-side 200 MB limit. Please use a smaller dataset.'
        } else if (response.status === 422) {
          // message already extracted from detail above
        }

        throw new Error(message)
      }

      setUploadSuccess(true)
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred during upload.'
      setUploadServerError(msg)
    } finally {
      setUploadLoading(false)
    }
  }, [selectedFile])

  // ── Polling ─────────────────────────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }, [])

  const pollJobStatus = useCallback(
    async (jobId: string) => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/admin/retrain/${jobId}`, {
          headers: { ...getAuthHeaders() },
        })
        if (!response.ok) {
          throw new Error(`Status check failed (HTTP ${response.status}).`)
        }
        const job: RetrainJob = await response.json()
        setCurrentJob(job)

        if (job.status === 'completed' || job.status === 'failed') {
          stopPolling()
        }
      } catch (err: unknown) {
        // On poll error, stop polling and surface the error
        stopPolling()
        const msg =
          err instanceof Error ? err.message : 'Failed to fetch job status.'
        setCurrentJob((prev) =>
          prev ? { ...prev, status: 'failed', message: msg } : null,
        )
      }
    },
    [stopPolling],
  )

  // ── Retrain trigger ─────────────────────────────────────────────────────────
  const handleRetrain = useCallback(async () => {
    setRetrainError(null)
    setCurrentJob(null)
    stopPolling()
    setRetrainLoading(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/retrain`, {
        method: 'POST',
        headers: { ...getAuthHeaders() },
      })

      if (!response.ok) {
        let message = `Retrain request failed (HTTP ${response.status}).`
        try {
          const data = await response.json()
          if (data?.detail) message = String(data.detail)
          else if (data?.message) message = String(data.message)
        } catch {
          // ignore
        }
        throw new Error(message)
      }

      const job: RetrainJob = await response.json()
      setCurrentJob(job)

      // Start polling every 3 seconds if not already terminal
      if (job.status !== 'completed' && job.status !== 'failed') {
        pollIntervalRef.current = setInterval(() => {
          pollJobStatus(job.job_id)
        }, 3000)
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'An unexpected error occurred while starting retrain.'
      setRetrainError(msg)
    } finally {
      setRetrainLoading(false)
    }
  }, [stopPolling, pollJobStatus])

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-8">
      {/* ── CSV Upload Section ─────────────────────────────────────────────── */}
      <section
        aria-labelledby="upload-heading"
        className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-6 flex flex-col gap-5"
      >
        <div>
          <h2
            id="upload-heading"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            Upload Training Dataset
          </h2>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
            Upload a CSV file containing at minimum a <code className="font-mono text-xs bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">text</code> column and a{' '}
            <code className="font-mono text-xs bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">label</code> column. Maximum file size: 200 MB.
          </p>
        </div>

        {/* File input */}
        <div className="flex flex-col gap-2">
          <label
            htmlFor="csv-upload"
            className="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Select CSV file
          </label>
          <input
            ref={fileInputRef}
            id="csv-upload"
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            disabled={uploadLoading}
            aria-describedby={fileError ? 'file-error' : undefined}
            className={[
              'block w-full text-sm text-gray-700 dark:text-gray-300',
              'file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0',
              'file:text-sm file:font-semibold',
              'file:bg-blue-50 file:text-blue-700 dark:file:bg-blue-900/30 dark:file:text-blue-300',
              'hover:file:bg-blue-100 dark:hover:file:bg-blue-900/50',
              'file:cursor-pointer file:transition-colors',
              'file:min-h-[44px] file:inline-flex file:items-center',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'focus:outline-none focus-within:ring-2 focus-within:ring-blue-500 rounded-lg',
              fileError ? 'ring-1 ring-red-400 dark:ring-red-500' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          />

          {/* Selected file info */}
          {selectedFile && !fileError && (
            <p className="text-xs text-gray-700 dark:text-gray-300">
              Selected:{' '}
              <span className="font-medium text-gray-900 dark:text-gray-100">
                {selectedFile.name}
              </span>{' '}
              ({(selectedFile.size / (1024 * 1024)).toFixed(2)} MB)
            </p>
          )}

          {/* Client-side file error */}
          {fileError && (
            <p
              id="file-error"
              role="alert"
              className="text-sm text-red-600 dark:text-red-400 flex items-center gap-1.5"
            >
              <ErrorIcon />
              {fileError}
            </p>
          )}
        </div>

        {/* Server-side upload error */}
        {uploadServerError && (
          <div
            role="alert"
            className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-4 flex items-start gap-3"
          >
            <ErrorIcon />
            <p className="text-sm text-red-700 dark:text-red-400">{uploadServerError}</p>
          </div>
        )}

        {/* Upload success */}
        {uploadSuccess && (
          <div
            role="status"
            className="rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 p-4 flex items-center gap-3"
          >
            <svg
              className="w-4 h-4 flex-shrink-0 text-green-600 dark:text-green-400"
              fill="currentColor"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
            <p className="text-sm text-green-700 dark:text-green-400 font-medium">
              Dataset uploaded successfully.
            </p>
          </div>
        )}

        {/* Upload button */}
        <button
          type="button"
          onClick={handleUpload}
          disabled={!selectedFile || uploadLoading || !!fileError}
          className={[
            'self-start min-h-[44px] rounded-lg px-5 py-2 text-sm font-semibold',
            'bg-blue-600 hover:bg-blue-700 active:bg-blue-800',
            'text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
            'dark:focus:ring-offset-gray-800',
            'disabled:opacity-60 disabled:cursor-not-allowed',
            'transition-colors flex items-center gap-2',
          ].join(' ')}
        >
          {uploadLoading ? (
            <>
              <Spinner />
              Uploading…
            </>
          ) : (
            <>
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                />
              </svg>
              Upload Dataset
            </>
          )}
        </button>
      </section>

      {/* ── Retrain Section ────────────────────────────────────────────────── */}
      <section
        aria-labelledby="retrain-heading"
        className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-6 flex flex-col gap-5"
      >
        <div>
          <h2
            id="retrain-heading"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            Retrain Model
          </h2>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
            Trigger a full model retrain using all available training data. The job runs
            asynchronously — status updates every 3 seconds.
          </p>
        </div>

        {/* Retrain error */}
        {retrainError && (
          <div
            role="alert"
            className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 p-4 flex items-start gap-3"
          >
            <ErrorIcon />
            <p className="text-sm text-red-700 dark:text-red-400">{retrainError}</p>
          </div>
        )}

        {/* Job status display */}
        {currentJob && (
          <div
            className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-4 flex flex-col gap-3"
            aria-live="polite"
            aria-atomic="true"
          >
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Job status:
              </span>
              <JobStatusBadge status={currentJob.status} />
            </div>

            <p className="text-xs text-gray-700 dark:text-gray-300 font-mono">
              Job ID: {currentJob.job_id}
            </p>

            {currentJob.message && (
              <p className="text-sm text-gray-700 dark:text-gray-300">{currentJob.message}</p>
            )}

            {/* Progress indicator for running jobs */}
            {(currentJob.status === 'pending' || currentJob.status === 'running') && (
              <div className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400">
                <Spinner />
                <span>Polling for updates every 3 seconds…</span>
              </div>
            )}
          </div>
        )}

        {/* Retrain button */}
        <button
          type="button"
          onClick={handleRetrain}
          disabled={
            retrainLoading ||
            currentJob?.status === 'pending' ||
            currentJob?.status === 'running'
          }
          className={[
            'self-start min-h-[44px] rounded-lg px-5 py-2 text-sm font-semibold',
            'bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800',
            'text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
            'dark:focus:ring-offset-gray-800',
            'disabled:opacity-60 disabled:cursor-not-allowed',
            'transition-colors flex items-center gap-2',
          ].join(' ')}
        >
          {retrainLoading ? (
            <>
              <Spinner />
              Starting retrain…
            </>
          ) : (
            <>
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Retrain Model
            </>
          )}
        </button>
      </section>
    </div>
  )
}
