import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { listDocuments, createDocument, uploadDocument, createCommit, listBranches } from '../api'

export default function Upload() {
  const { repoId } = useParams()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [branches, setBranches] = useState([])
  const [mode, setMode] = useState('commit')     // 'commit' = update existing | 'new' = create + upload
  const [form, setForm] = useState({ part_number: '', title: '', doc_type: 'detail' })
  const [selectedDoc, setSelectedDoc] = useState('')
  const [selectedBranch, setSelectedBranch] = useState('')
  const [file, setFile] = useState(null)
  const [author, setAuthor] = useState('')
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    Promise.all([listDocuments(repoId), listBranches(repoId)]).then(([d, b]) => {
      setDocuments(d)
      setBranches(b.filter(b => b.status === 'open'))
    })
  }, [repoId])

  const handleSubmit = async e => {
    e.preventDefault()
    if (!file) return alert('Select a PDF file')
    if (!author.trim()) return alert('Enter your name')
    setLoading(true)
    setStatus(null)
    try {
      if (mode === 'new') {
        // create document metadata first, then upload the initial PDF
        const doc = await createDocument(repoId, form)
        const fd = new FormData()
        fd.append('file', file)
        fd.append('author', author)
        fd.append('message', message || 'Initial upload')
        await uploadDocument(repoId, doc.id, fd)
        setStatus({ type: 'success', message: `Document ${form.part_number} created and uploaded.` })
      } else {
        // commit a new version of an existing document
        const fd = new FormData()
        fd.append('doc_id', selectedDoc)
        fd.append('file', file)
        fd.append('author', author)
        fd.append('message', message)
        if (selectedBranch) fd.append('branch_id', selectedBranch)
        await createCommit(repoId, fd)
        setStatus({ type: 'success', message: 'Commit created successfully.' })
      }
      setTimeout(() => navigate(`/repos/${repoId}`), 1200)
    } catch (e) {
      setStatus({ type: 'error', message: e.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '560px' }}>
      <Link to={`/repos/${repoId}`} style={{ color: '#888', fontSize: '13px' }}>← Back to repository</Link>
      <h2 style={{ margin: '8px 0 20px' }}>Upload Drawing</h2>

      {/* Mode toggle */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '20px', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>
        <button onClick={() => setMode('commit')} style={{ flex: 1, padding: '8px', border: 'none', background: mode === 'commit' ? '#1a1a2e' : '#fff', color: mode === 'commit' ? '#fff' : '#333', cursor: 'pointer' }}>
          Update Existing Drawing
        </button>
        <button onClick={() => setMode('new')} style={{ flex: 1, padding: '8px', border: 'none', background: mode === 'new' ? '#1a1a2e' : '#fff', color: mode === 'new' ? '#fff' : '#333', cursor: 'pointer' }}>
          New Drawing
        </button>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>

        {mode === 'commit' ? (
          <>
            <label style={labelStyle}>Document</label>
            <select value={selectedDoc} onChange={e => setSelectedDoc(e.target.value)} required style={inputStyle}>
              <option value="">Select document…</option>
              {documents.map(d => <option key={d.id} value={d.id}>{d.part_number} — {d.title}</option>)}
            </select>

            <label style={labelStyle}>Branch (optional — leave blank for main)</label>
            <select value={selectedBranch} onChange={e => setSelectedBranch(e.target.value)} style={inputStyle}>
              <option value="">Main</option>
              {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </>
        ) : (
          <>
            <label style={labelStyle}>Part Number</label>
            <input required placeholder="e.g. EVC-SA-8000" value={form.part_number}
              onChange={e => setForm({ ...form, part_number: e.target.value })} style={inputStyle} />
            <label style={labelStyle}>Title</label>
            <input required placeholder="e.g. Alternator Bracket Assembly" value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })} style={inputStyle} />
            <label style={labelStyle}>Type</label>
            <select value={form.doc_type} onChange={e => setForm({ ...form, doc_type: e.target.value })} style={inputStyle}>
              <option value="detail">Detail (single part)</option>
              <option value="assembly">Assembly (contains other parts)</option>
              <option value="part">Part</option>
            </select>
          </>
        )}

        <label style={labelStyle}>PDF Drawing *</label>
        <input type="file" accept=".pdf" required onChange={e => setFile(e.target.files[0])} style={inputStyle} />

        <label style={labelStyle}>Your Name *</label>
        <input required placeholder="e.g. Dan Manoim" value={author}
          onChange={e => setAuthor(e.target.value)} style={inputStyle} />

        <label style={labelStyle}>Commit Message</label>
        <input placeholder={mode === 'new' ? 'Initial upload' : 'Describe what changed'}
          value={message} onChange={e => setMessage(e.target.value)} style={inputStyle} />

        <button type="submit" disabled={loading}
          style={{ padding: '10px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', marginTop: '4px' }}>
          {loading ? 'Uploading…' : mode === 'new' ? 'Create & Upload' : 'Commit Drawing'}
        </button>
      </form>

      {status && (
        <p style={{ marginTop: '16px', color: status.type === 'success' ? 'green' : 'red' }}>
          {status.message}
        </p>
      )}
    </div>
  )
}

const inputStyle = { padding: '8px', border: '1px solid #ccc', borderRadius: '4px', fontSize: '14px' }
const labelStyle = { fontSize: '13px', color: '#555', marginBottom: '-6px' }
