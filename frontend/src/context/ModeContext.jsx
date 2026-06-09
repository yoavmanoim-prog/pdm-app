import { createContext, useContext, useState } from 'react'

const ModeContext = createContext()

const isLocalhost = window.location.hostname === 'localhost'

export function ModeProvider({ children }) {
  const [mode, setMode] = useState(
    () => localStorage.getItem('vaultMode') || (isLocalhost ? 'local' : 'remote')
  )
  const [remoteUrl, setRemoteUrlState] = useState(
    () => localStorage.getItem('remoteVaultUrl') || ''
  )

  function switchMode(m) {
    setMode(m)
    localStorage.setItem('vaultMode', m)
  }

  function setRemoteUrl(url) {
    const trimmed = url.trim().replace(/\/$/, '')
    setRemoteUrlState(trimmed)
    localStorage.setItem('remoteVaultUrl', trimmed)
  }

  // the base URL api.js should use for the current mode
  function apiBase() {
    if (mode === 'local') return 'http://localhost:8000'
    // on CloudFront: relative path (same domain); on localhost: absolute remote URL
    if (!isLocalhost) return '/api'
    return remoteUrl ? `${remoteUrl}/api` : '/api'
  }

  return (
    <ModeContext.Provider value={{ mode, switchMode, remoteUrl, setRemoteUrl, apiBase }}>
      {children}
    </ModeContext.Provider>
  )
}

export function useMode() {
  return useContext(ModeContext)
}
