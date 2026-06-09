import { useEffect, useState, useRef } from 'react'
import { getWatchStatus, watchCommit } from '../api'

const badge = {
  committed: { background: '#d4edda', color: '#155724', label: 'committed' },
  modified:  { background: '#fff3cd', color: '#856404', label: 'modified'  },
  untracked: { background: '#f0f0f0', color: '#555',    label: 'untracked' },
}

export default function WorkingDirectory({ repoId }) {
  const [files, setFiles]       = useState([])
  const [watchDir, setWatchDir] = useState('')
  const [error, setError]       = useState(null)
  const [committing, setCommitting] = useState(null)
  const intervalRef = useRef(null)

  const refresh = () => {
    getWatchStatus(repoId)
      .then(d => { setFiles(d.files); setWatchDir(d.watch_dir); setError(null) })
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    refresh()
    intervalRef.current = setInterval(refresh, 5000)
    return () => clearInterval(intervalRef.current)
  }, [repoId])

  // repo has no watch_path set
  if (error?.includes('No watch directory')) return (
    <div style={{ padding: '16px', background: '#f5f5f5', borderRadius: '6px', color: '#666' }}>
      No directory linked to this repository.
      <br />
      <span style={{ fontSize: '13px' }}>
        Repos created on the remote vault don't have a local directory. Clone or create a new local repo to use Working Dir.
      </span>
    </div>
  )

  if (error) return (
    <div style={{ padding: '12px', background: '#fff3cd', borderRadius: '6px', color: '#856404' }}>
      {error}
    </div>
  )

  return (
    <div>
      {watchDir && (
        <div style={{ fontSize: '12px', color: '#888', marginBottom: '12px' }}>
          Watching <code style={{ background: '#f0f0f0', padding: '1px 6px', borderRadius: '3px' }}>{watchDir}</code>
          {' '}— refreshes every 5 s
        </div>
      )}

      {files.length === 0 && watchDir && (
        <p style={{ color: '#aaa' }}>No PDF files found in this directory.</p>
      )}

      {files.map(f => (
        <div key={f.filename}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            padding: '10px 12px', border: '1px solid #eee',
            borderRadius: committing === f.filename ? '4px 4px 0 0' : '4px',
            marginBottom: committing === f.filename ? '0' : '6px',
            background: '#fff',
          }}>
            <span style={{ padding: '2px 8px', borderRadius: '3px', fontSize: '11px', fontWeight: 600, ...badge[f.status] }}>
              {badge[f.status].label}
            </span>
            <span style={{ flex: 1 }}>
              <code style={{ fontSize: '13px' }}>{f.filename}</code>
              {f.title && <span style={{ marginLeft: '8px', color: '#666', fontSize: '13px' }}>{f.title}</span>}
            </span>
            <code style={{ fontSize: '11px', color: '#aaa' }}>{f.hash}</code>
            {f.status !== 'committed' && (
              <button onClick={() => setCommitting(committing === f.filename ? null : f.filename)} style={btnStyle}>
                {committing === f.filename ? 'Cancel' : 'Commit'}
              </button>
            )}
          </div>

          {committing === f.filename && (
            <CommitForm repoId={repoId} file={f} onDone={() => { setCommitting(null); refresh() }} />
          )}
        </div>
      ))}
    </div>
  )
}

function CommitForm({ repoId, file, onDone }) {
  const [author, setAuthor]         = useState('')
  const [message, setMessage]       = useState('')
  const [partNumber, setPartNumber] = useState(file.part_number || '')
  const [title, setTitle]           = useState(file.title || '')
  const [docType, setDocType]       = useState('detail')
  const [loading, setLoading]       = useState(false)
  const [err, setErr]               = useState(null)

  const handleSubmit = async e => {
    e.preventDefault()
    if (!author.trim()) return setErr('Enter your name')
    if (!message.trim()) return setErr('Enter a commit message')
    setLoading(true); setErr(null)
    try {
      const fd = new FormData()
      fd.append('filename', file.filename)
      fd.append('author', author)
      fd.append('message', message)
      if (file.doc_id) {
        fd.append('doc_id', file.doc_id)
      } else {
        fd.append('part_number', partNumber)
        fd.append('title', title)
        fd.append('doc_type', docType)
      }
      await watchCommit(repoId, fd)
      onDone()
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{
      padding: '14px 16px', background: '#f9f9f9',
      border: '1px solid #eee', borderTop: 'none',
      borderRadius: '0 0 4px 4px', marginBottom: '6px',
      display: 'flex', flexDirection: 'column', gap: '8px',
    }}>
      {!file.doc_id && (
        <>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input required placeholder="Part number (e.g. FW-PT-0001)" value={partNumber}
              onChange={e => setPartNumber(e.target.value)} style={{ ...inputStyle, flex: 1 }} />
            <select value={docType} onChange={e => setDocType(e.target.value)} style={inputStyle}>
              <option value="detail">Detail</option>
              <option value="assembly">Assembly</option>
            </select>
          </div>
          <input required placeholder="Title (e.g. SMA End Cap)" value={title}
            onChange={e => setTitle(e.target.value)} style={inputStyle} />
        </>
      )}
      <input required placeholder="Your name" value={author}
        onChange={e => setAuthor(e.target.value)} style={inputStyle} />
      <input required placeholder="Commit message" value={message}
        onChange={e => setMessage(e.target.value)} style={inputStyle} />
      {err && <p style={{ color: 'red', margin: 0, fontSize: '13px' }}>{err}</p>}
      <button type="submit" disabled={loading} style={{ ...btnStyle, alignSelf: 'flex-start' }}>
        {loading ? 'Committing…' : 'Commit from disk'}
      </button>
    </form>
  )
}

const btnStyle = { padding: '5px 14px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }
const inputStyle = { padding: '7px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '13px', background: '#fff' }
