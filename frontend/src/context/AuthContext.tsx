/**
 * AuthContext — provides authentication state to the whole app.
 *
 * Stores the JWT in localStorage under 'auth_token'.
 * Exposes: token, isAuthenticated, isAdmin, login(), logout()
 */

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

const TOKEN_KEY = 'auth_token'
const ADMIN_TOKEN_KEY = 'admin_token'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  isAdmin: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))

  const login = useCallback(async (username: string, password: string) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Invalid username or password')
    }

    const data = await response.json()
    const jwt = data.access_token

    // Store in both keys so existing admin guards still work
    localStorage.setItem(TOKEN_KEY, jwt)
    localStorage.setItem(ADMIN_TOKEN_KEY, jwt)
    setToken(jwt)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ADMIN_TOKEN_KEY)
    setToken(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        isAuthenticated: !!token,
        isAdmin: !!token, // all logged-in users can access admin for this project
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** Returns auth headers for API calls */
export function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}
