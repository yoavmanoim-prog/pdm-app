import { Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ModeProvider, useMode } from './context/ModeContext'
import { useAuth } from './context/AuthContext'
import ModeToggle from './components/ModeToggle'
import Dashboard from './pages/Dashboard'
import Repository from './pages/Repository'
import BranchView from './pages/BranchView'
import Upload from './pages/Upload'
import DocumentViewer from './pages/DocumentViewer'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Admin from './pages/Admin'
import Roles from './pages/Roles'

// Gate for any page that needs a logged-in user. While the session is still
// being restored from a saved token we render nothing decisive (no redirect),
// otherwise a logged-in user would flash the login page on every refresh.
function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <p>Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

// Privilege gate. A logged-in user lacking the privilege gets bounced to the
// dashboard; the backend also enforces it, so this is convenience, not security.
function RequirePrivilege({ privilege, children }) {
  const { user, loading, can } = useAuth()
  if (loading) return <p>Loading…</p>
  if (!user) return <Navigate to="/login" replace />
  if (!can(privilege)) return <Navigate to="/" replace />
  return children
}

const navLink = { fontSize: 13, color: 'var(--text-muted)', padding: '6px 10px', borderRadius: 6 }

function UserMenu() {
  const { user, logout, can } = useAuth()
  const navigate = useNavigate()
  if (!user) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {can('manage_users') && <Link to="/admin" style={navLink}>Users</Link>}
      {can('manage_roles') && <Link to="/roles" style={navLink}>Roles</Link>}
      {/* user chip */}
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)',
        background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 999, padding: '4px 6px 4px 12px', marginLeft: 6,
      }}>
        {user.email}
        <button
          onClick={() => { logout(); navigate('/login') }}
          title="Log out"
          style={{ fontSize: 12, padding: '3px 10px', border: '1px solid var(--border)', borderRadius: 999, background: 'var(--surface-3)', color: 'var(--text)' }}>
          Log out
        </button>
      </span>
    </div>
  )
}

function AppContent() {
  const { vaultKey } = useMode()
  return (
    <Routes key={vaultKey}>
      {/* public — these are how you obtain a token, so they can't require one */}
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* protected */}
      <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
      <Route path="/repos/:repoId" element={<RequireAuth><Repository /></RequireAuth>} />
      <Route path="/repos/:repoId/upload" element={<RequireAuth><Upload /></RequireAuth>} />
      <Route path="/repos/:repoId/branches/:branchId" element={<RequireAuth><BranchView /></RequireAuth>} />
      <Route path="/repos/:repoId/documents/:docId" element={<RequireAuth><DocumentViewer /></RequireAuth>} />

      {/* admin-only (privilege-gated) */}
      <Route path="/admin" element={<RequirePrivilege privilege="manage_users"><Admin /></RequirePrivilege>} />
      <Route path="/roles" element={<RequirePrivilege privilege="manage_roles"><Roles /></RequirePrivilege>} />
    </Routes>
  )
}

export default function App() {
  return (
    <ModeProvider>
      {/* sticky full-width header bar */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 30,
        background: 'rgba(13, 20, 33, 0.85)', backdropFilter: 'blur(8px)',
        borderBottom: '1px solid var(--border)',
      }}>
        <nav style={{
          maxWidth: '1180px', margin: '0 auto', padding: '12px 24px',
          display: 'flex', alignItems: 'center', gap: '16px',
        }}>
          <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* logo chip */}
            <span style={{
              display: 'grid', placeItems: 'center', width: 30, height: 30, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--accent), #0b6b82)', color: '#021318',
              fontSize: 16, boxShadow: '0 2px 8px -2px var(--accent)',
            }}>⚙</span>
            <span style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.01em' }}>
              MechDocs <span style={{ color: 'var(--accent-bright)' }}>PDM</span>
            </span>
          </Link>
          <span style={{ color: 'var(--text-faint)', fontSize: '12px', borderLeft: '1px solid var(--border)', paddingLeft: 16 }}>
            Metal Factory Drawing Management
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
            <ModeToggle />
            <UserMenu />
          </div>
        </nav>
      </header>

      <main style={{ maxWidth: '1180px', margin: '0 auto', padding: '28px 24px 60px' }}>
        <AppContent />
      </main>
    </ModeProvider>
  )
}
