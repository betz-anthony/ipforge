import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { authApi, type AuthUser } from '../api/client'

interface AuthCtx {
  user: AuthUser | null
  loading: boolean
  login:  (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser]       = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('ipam_token')
    const stored = localStorage.getItem('ipam_user')
    if (token && stored) {
      try {
        setUser(JSON.parse(stored))
      } catch {
        localStorage.removeItem('ipam_user')
      }
    }
    setLoading(false)
  }, [])

  async function login(username: string, password: string) {
    const data = await authApi.login(username, password)
    localStorage.setItem('ipam_token', data.access_token)
    const u: AuthUser = { username: data.username, role: data.role as AuthUser['role'] }
    localStorage.setItem('ipam_user', JSON.stringify(u))
    setUser(u)
  }

  function logout() {
    localStorage.removeItem('ipam_token')
    localStorage.removeItem('ipam_user')
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthCtx {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
