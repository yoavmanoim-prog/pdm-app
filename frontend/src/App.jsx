import { Routes, Route, Link, useParams } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Repository from './pages/Repository'
import BranchView from './pages/BranchView'
import Upload from './pages/Upload'
import DocumentViewer from './pages/DocumentViewer'

export default function App() {
  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '1100px', margin: '0 auto', padding: '20px' }}>
      <nav style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '28px', borderBottom: '2px solid #1a1a2e', paddingBottom: '12px' }}>
        <Link to="/" style={{ textDecoration: 'none' }}>
          <strong style={{ fontSize: '18px', color: '#1a1a2e' }}>⚙ MechDocs PDM</strong>
        </Link>
        <span style={{ color: '#888', fontSize: '13px' }}>Metal Factory Drawing Management</span>
      </nav>

      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/repos/:repoId" element={<Repository />} />
        <Route path="/repos/:repoId/upload" element={<Upload />} />
        <Route path="/repos/:repoId/branches/:branchId" element={<BranchView />} />
        {/* document viewer with version history and PDF diff */}
        <Route path="/repos/:repoId/documents/:docId" element={<DocumentViewer />} />
      </Routes>
    </div>
  )
}
