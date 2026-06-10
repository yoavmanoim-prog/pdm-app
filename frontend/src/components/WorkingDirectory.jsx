import { useEffect, useState, useRef } from 'react'
import { getWatchStatus, watchCommit, watchPreviewUrl, listBranches, listDocuments, addBomEntry } from '../api'
import { useRepo } from '../context/RepoContext'

const badge = {
  committed: { background: '#d4edda', color: '#155724', label: 'committed' },
  modified:  { background: '#fff3cd', color: '#856404', label: 'modified'  },
  untracked: { background: '#f0f0f0', color: '#555',    label: 'untracked' },
}

export default function WorkingDirectory({ repoId }) {
  const { refresh } = useRepo()
  const [files, setFiles]       = useState([])
  const [watchDir, setWatchDir] = useState('')
  const [error, setError]       = useState(null)
  const [committing, setCommitting] = useState(null)
  const [preview, setPreview]   = useState(null)
  const intervalRef = useRef(null)

  const localRefresh = () => {
    getWatchStatus(repoId)
      .then(d => { setFiles(d.files); setWatchDir(d.watch_dir); setError(null) })
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    localRefresh()
    intervalRef.current = setInterval(localRefresh, 5000)
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
      {/* ── PDF preview modal ── */}
      {preview && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', flexDirection: 'column' }}
          onClick={() => setPreview(null)}>
          <div style={{ background: '#fff', margin: '40px auto', width: '90%', maxWidth: '900px', height: 'calc(100vh - 80px)', borderRadius: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 16px', borderBottom: '1px solid #eee' }}>
              <span style={{ fontSize: '14px', fontWeight: 600 }}>{preview}</span>
              <button onClick={() => setPreview(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#666' }}>✕</button>
            </div>
            <iframe src={watchPreviewUrl(repoId, preview)} style={{ flex: 1, border: 'none' }} title={preview} />
          </div>
        </div>
      )}

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
              <code
                onClick={() => setPreview(f.filename)}
                style={{ fontSize: '13px', cursor: 'pointer', color: '#1a1a2e', textDecoration: 'underline dotted' }}
                title="Click to preview"
              >{f.filename}</code>
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
            <CommitForm repoId={repoId} file={f} onDone={() => { setCommitting(null); localRefresh(); refresh() }} />
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
  const [docType, setDocType]       = useState(file.doc_type || 'detail')
  const [branchId, setBranchId]     = useState('')
  const [branches, setBranches]     = useState([])
  // sons = BOM entries to create after commit (only for assemblies)
  const [sons, setSons]             = useState([])
  const [allDocs, setAllDocs]       = useState([])
  const [loading, setLoading]       = useState(false)
  const [err, setErr]               = useState(null)

  const isAssembly = docType === 'assembly' || file.doc_type === 'assembly'

  useEffect(() => {
    listBranches(repoId).then(b => setBranches(b.filter(x => x.status === 'open'))).catch(() => {})
    if (isAssembly) listDocuments(repoId).then(setAllDocs).catch(() => {})
  }, [repoId, isAssembly])

  const addSon = () => setSons(s => [...s, { part_number: '', qty: 1, position: '' }])
  const updateSon = (i, field, val) => setSons(s => s.map((x, idx) => idx === i ? { ...x, [field]: val } : x))
  const removeSon = (i) => setSons(s => s.filter((_, idx) => idx !== i))

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
      if (branchId) fd.append('branch_id', branchId)
      if (file.doc_id) {
        fd.append('doc_id', file.doc_id)
      } else {
        fd.append('part_number', partNumber)
        fd.append('title', title)
        fd.append('doc_type', docType)
      }
      const result = await watchCommit(repoId, fd)

      // create BOM entries for each son after commit succeeds
      const assemblyDocId = file.doc_id || result?.document_id
      if (assemblyDocId && sons.length > 0) {
        const docByPart = Object.fromEntries(allDocs.map(d => [d.part_number.toUpperCase(), d]))
        for (const son of sons) {
          const comp = docByPart[son.part_number.toUpperCase()]
          if (!comp) continue
          await addBomEntry(repoId, assemblyDocId, {
            component_id: comp.id,
            quantity: parseInt(son.qty) || 1,
            position: son.position || null,
            item_type: comp.doc_type === 'assembly' ? 'assembly' : 'part',
          }).catch(() => {})   // skip duplicates silently
        }
      }

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
      <select value={branchId} onChange={e => setBranchId(e.target.value)} style={inputStyle}>
        <option value="">main (default)</option>
        {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
      </select>
      <input required placeholder="Your name" value={author}
        onChange={e => setAuthor(e.target.value)} style={inputStyle} />
      <input required placeholder="Commit message" value={message}
        onChange={e => setMessage(e.target.value)} style={inputStyle} />
      {/* ── Sons / BOM section — only for assemblies ── */}
      {isAssembly && (
        <div style={{ border: '1px solid #ddd', borderRadius: '6px', padding: '10px 12px', background: '#fff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#555' }}>Component drawings (sons)</span>
            <button type="button" onClick={addSon}
              style={{ fontSize: '12px', padding: '2px 10px', border: '1px solid #1a1a2e', borderRadius: '4px', cursor: 'pointer', background: 'none', color: '#1a1a2e' }}>
              + Add
            </button>
          </div>

          {sons.length === 0 && (
            <p style={{ fontSize: '12px', color: '#aaa', margin: 0 }}>No components yet — click + Add to link child drawings.</p>
          )}

          {sons.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: '6px', marginBottom: '6px', alignItems: 'center' }}>
              <input
                placeholder="Part number"
                value={s.part_number}
                onChange={e => updateSon(i, 'part_number', e.target.value)}
                list={`docs-list-${i}`}
                style={{ ...inputStyle, flex: 2 }}
              />
              <datalist id={`docs-list-${i}`}>
                {allDocs.map(d => <option key={d.id} value={d.part_number}>{d.title}</option>)}
              </datalist>
              <input
                placeholder="Qty"
                type="number" min="1"
                value={s.qty}
                onChange={e => updateSon(i, 'qty', e.target.value)}
                style={{ ...inputStyle, width: '56px' }}
              />
              <input
                placeholder="Pos"
                value={s.position}
                onChange={e => updateSon(i, 'position', e.target.value)}
                style={{ ...inputStyle, width: '56px' }}
              />
              <button type="button" onClick={() => removeSon(i)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#aaa', fontSize: '16px', padding: '0 4px' }}>✕</button>
            </div>
          ))}
        </div>
      )}

      {err && <p style={{ color: 'red', margin: 0, fontSize: '13px' }}>{err}</p>}
      <button type="submit" disabled={loading} style={{ ...btnStyle, alignSelf: 'flex-start' }}>
        {loading ? 'Committing…' : 'Commit from disk'}
      </button>
    </form>
  )
}

const btnStyle = { padding: '5px 14px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }
const inputStyle = { padding: '7px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '13px', background: '#fff' }
