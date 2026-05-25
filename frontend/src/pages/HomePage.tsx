import { SubmissionForm } from '../components/SubmissionForm'

export function HomePage() {
  return (
    <div className="flex flex-col items-center gap-6 w-full">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 text-center">
        Fake News Detector
      </h1>
      <p className="text-gray-700 dark:text-gray-300 text-center max-w-xl w-full px-2">
        Paste a news article or enter a URL to check whether the content is real or fake.
      </p>
      <SubmissionForm />
    </div>
  )
}
