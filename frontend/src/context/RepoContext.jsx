import { createContext, useContext, useState, useCallback } from 'react'

const RepoContext = createContext()

// Wraps the repository page. Any component can call refresh() after an action
// and every other component that reads version will re-fetch automatically.
export function RepoProvider({ children }) {
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion(v => v + 1), [])
  return (
    <RepoContext.Provider value={{ version, refresh }}>
      {children}
    </RepoContext.Provider>
  )
}

export function useRepo() {
  return useContext(RepoContext)
}
