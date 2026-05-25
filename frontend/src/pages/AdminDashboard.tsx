import { AdminPanel } from '../components/AdminPanel'
import { AnalyticsWidgets } from '../components/AnalyticsWidgets'

export function AdminDashboard() {
  return (
    <div className="flex flex-col gap-6 w-full">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Admin Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          Manage training data, retrain the model, and view analytics.
        </p>
      </div>

      {/* AdminPanel: CSV upload + retrain trigger (task 12.1) */}
      <div className="w-full">
        <AdminPanel />
      </div>

      {/* Analytics widgets: total submissions, Real/Fake %, model accuracy (task 12.2) */}
      <div className="w-full">
        <AnalyticsWidgets />
      </div>
    </div>
  )
}
