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

function UserMenu() {
  const { user, logout, can } = useAuth()
  const navigate = useNavigate()
  if (!user) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      {can('manage_users') && <Link to="/admin" style={{ fontSize: 13, color: '#1a1a2e' }}>Users</Link>}
      {can('manage_roles') && <Link to="/roles" style={{ fontSize: 13, color: '#1a1a2e' }}>Roles</Link>}
      <span style={{ fontSize: 13, color: '#666' }}>{user.email}</span>
      <button
        onClick={() => { logout(); navigate('/login') }}
        style={{ fontSize: 12, padding: '4px 10px', border: '1px solid #ccc', borderRadius: 4, background: '#fff', cursor: 'pointer' }}>
        Log out
      </button>
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
      <div style={{ fontFamily: 'sans-serif', maxWidth: '1100px', margin: '0 auto', padding: '20px', position: 'relative' }}>
        <nav style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '28px', borderBottom: '2px solid #1a1a2e', paddingBottom: '12px' }}>
          <Link to="/" style={{ textDecoration: 'none' }}>
            <strong style={{ fontSize: '18px', color: '#1a1a2e' }}>⚙ MechDocs PDM</strong>
          </Link>
          <span style={{ color: '#888', fontSize: '13px' }}>Metal Factory Drawing Management</span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16 }}>
            <ModeToggle />
            <UserMenu />
          </div>
        </nav>

        <AppContent />
      </div>
    </ModeProvider>
  )
}
