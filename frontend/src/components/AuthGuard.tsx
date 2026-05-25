import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// ── Legacy helpers kept for backward compatibility with existing code ─────────

const TOKEN_KEY = 'auth_token'
const ADMIN_TOKEN_KEY = 'admin_token'

export function getAdminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY) || localStorage.getItem(ADMIN_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
  localStorage.removeItem(TOKEN_KEY)
}

// ── AuthGuard component ───────────────────────────────────────────────────────

interface AuthGuardProps {
  children: React.ReactNode
  /** If true, redirects to /login instead of /admin/login */
  appLevel?: boolean
}

/**
 * Redirects unauthenticated users to the login page.
 * - appLevel=true  → redirects to /login  (whole-app guard)
 * - appLevel=false → redirects to /admin/login (admin-only guard, legacy)
 */
export function AuthGuard({ children, appLevel = false }: AuthGuardProps) {
  const location = useLocation()
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    // Always redirect to /login
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
