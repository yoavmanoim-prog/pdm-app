import { Routes, Route, Link } from 'react-router-dom'
import { ModeProvider, useMode } from './context/ModeContext'
import ModeToggle from './components/ModeToggle'
import Dashboard from './pages/Dashboard'
import Repository from './pages/Repository'
import BranchView from './pages/BranchView'
import Upload from './pages/Upload'
import DocumentViewer from './pages/DocumentViewer'

function AppContent() {
  const { vaultKey } = useMode()
  return (
    <Routes key={vaultKey}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/repos/:repoId" element={<Repository />} />
      <Route path="/repos/:repoId/upload" element={<Upload />} />
      <Route path="/repos/:repoId/branches/:branchId" element={<BranchView />} />
      <Route path="/repos/:repoId/documents/:docId" element={<DocumentViewer />} />
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
          <div style={{ marginLeft: 'auto' }}>
            <ModeToggle />
          </div>
        </nav>

        <AppContent />
      </div>
    </ModeProvider>
  )
}
