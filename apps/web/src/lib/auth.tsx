import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken, type Schemas } from './client'

type User = Schemas['UserOut']
type Ctx = { user: User | null; loading: boolean; signIn: (t: string, u: User) => void; signOut: () => void; refresh: () => Promise<void> }

const AuthCtx = createContext<Ctx>({ user: null, loading: true, signIn: () => {}, signOut: () => {}, refresh: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return }
    const { data } = await api.GET('/auth/me')
    setUser(data ?? null)
    if (!data) setToken(null)
    setLoading(false)
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  return (
    <AuthCtx.Provider value={{
      user, loading, refresh,
      signIn: (t, u) => { setToken(t); setUser(u) },
      signOut: () => { setToken(null); setUser(null) },
    }}>{children}</AuthCtx.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthCtx)
