import { createContext, useContext, useEffect, useState } from 'react'
import * as api from '../api'

// Holds the logged-in user for the whole app. Think of it as the coat-check
// desk: it remembers your wristband (token) and who you are (user) so every
// page can ask "am I logged in? am I an admin?" without re-checking the server.
const AuthContext = createContext()

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // 'loading' guards the first render: while we restore the session from a saved
  // token we don't yet know if the user is logged in, so we must not redirect.
  const [loading, setLoading] = useState(true)

  // On startup, if a token is in storage, ask the backend who it belongs to.
  // A stale/expired token makes /auth/me 401 → api.js clears it → user stays null.
  useEffect(() => {
    if (!api.getToken()) { setLoading(false); return }
    api.getMe()
      .then(setUser)
      .catch(() => api.setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email, password) {
    const { access_token, user } = await api.login({ email, password })
    api.setToken(access_token)
    setUser(user)
    return user
  }

  async function signup(email, password, full_name) {
    const { access_token, user } = await api.signup({ email, password, full_name })
    api.setToken(access_token)
    setUser(user)
    return user
  }

  function logout() {
    api.setToken(null)
    setUser(null)
  }

  const value = { user, loading, login, signup, logout, isAdmin: user?.role === 'admin' }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
