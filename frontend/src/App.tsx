import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { AppLayout } from './components/AppLayout'
import { AuthGuard } from './components/AuthGuard'
import { HomePage } from './pages/HomePage'
import { ResultPage } from './pages/ResultPage'
import { HistoryPage } from './pages/HistoryPage'
import { AdminDashboard } from './pages/AdminDashboard'
import { LoginPage } from './pages/LoginPage'

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public route — login page (no layout) */}
          <Route path="/login" element={<LoginPage />} />

          {/* Legacy admin login route — redirects to /login */}
          <Route path="/admin/login" element={<LoginPage />} />

          {/* Main app routes — publicly accessible (no auth required) */}
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="/result/:id" element={<ResultPage />} />
            <Route path="/history" element={<HistoryPage />} />
            {/* Admin route — requires authentication */}
            <Route
              path="/admin"
              element={
                <AuthGuard>
                  <AdminDashboard />
                </AuthGuard>
              }
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
