import { useEffect, useState, useRef } from 'react'
import { getWatchStatus, watchCommit, watchPreviewUrl, listBranches, listDocuments, addBomEntry } from '../api'
import { useRepo } from '../context/RepoContext'

const badge = {
  committed: { background: 'var(--success-bg)', color: 'var(--success)', label: 'committed' },
  modified:  { background: 'var(--warning-bg)', color: 'var(--warning)', label: 'modified'  },
  untracked: { background: 'var(--surface-2)', color: 'var(--text-muted)',    label: 'untracked' },
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
    <div style={{ padding: '16px', background: 'var(--surface-2)', borderRadius: '6px', color: 'var(--text-muted)' }}>
      No directory linked to this repository.
      <br />
      <span style={{ fontSize: '13px' }}>
        Repos created on the remote vault don't have a local directory. Clone or create a new local repo to use Working Dir.
      </span>
    </div>
  )

  if (error) return (
    <div style={{ padding: '12px', background: 'var(--warning-bg)', borderRadius: '6px', color: 'var(--warning)' }}>
      {error}
    </div>
  )

  return (
    <div>
      {/* ── PDF preview modal ── */}
      {preview && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000, display: 'flex', flexDirection: 'column' }}
          onClick={() => setPreview(null)}>
          <div style={{ background: 'var(--surface)', margin: '40px auto', width: '90%', maxWidth: '900px', height: 'calc(100vh - 80px)', borderRadius: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 16px', borderBottom: '1px solid var(--border-soft)' }}>
              <span style={{ fontSize: '14px', fontWeight: 600 }}>{preview}</span>
              <button onClick={() => setPreview(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: 'var(--text-muted)' }}>✕</button>
            </div>
            <iframe src={watchPreviewUrl(repoId, preview)} style={{ flex: 1, border: 'none' }} title={preview} />
          </div>
        </div>
      )}

      {watchDir && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
          Watching <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: '3px' }}>{watchDir}</code>
          {' '}— refreshes every 5 s
        </div>
      )}

      {files.length === 0 && watchDir && (
        <p style={{ color: 'var(--text-faint)' }}>No PDF files found in this directory.</p>
      )}

      {files.map(f => (
        <div key={f.filename}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '10px',
            padding: '10px 12px', border: '1px solid var(--border-soft)',
            borderRadius: committing === f.filename ? '4px 4px 0 0' : '4px',
            marginBottom: committing === f.filename ? '0' : '6px',
            background: 'var(--surface)',
          }}>
            <span style={{ padding: '2px 8px', borderRadius: '3px', fontSize: '11px', fontWeight: 600, ...badge[f.status] }}>
              {badge[f.status].label}
            </span>
            <span style={{ flex: 1 }}>
              <code
                onClick={() => setPreview(f.filename)}
                style={{ fontSize: '13px', cursor: 'pointer', color: 'var(--accent)', textDecoration: 'underline dotted' }}
                title="Click to preview"
              >{f.filename}</code>
              {f.title && <span style={{ marginLeft: '8px', color: 'var(--text-muted)', fontSize: '13px' }}>{f.title}</span>}
            </span>
            <code style={{ fontSize: '11px', color: 'var(--text-faint)' }}>{f.hash}</code>
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
  const [sons, setSons]             = useState([])    // component children (assemblies only)
  const [fathers, setFathers]       = useState([])    // parent assemblies (all types)
  const [allDocs, setAllDocs]       = useState([])
  const [loading, setLoading]       = useState(false)
  const [err, setErr]               = useState(null)

  const isAssembly = docType === 'assembly' || file.doc_type === 'assembly'
  const isPart = docType === 'part' || file.doc_type === 'part'
  const canHaveSons = isAssembly || isPart   // both assemblies and parts can have sons
  const allAssemblies = allDocs.filter(d => d.doc_type === 'assembly')

  useEffect(() => {
    listBranches(repoId).then(b => setBranches(b.filter(x => x.status === 'open'))).catch(() => {})
    listDocuments(repoId).then(setAllDocs).catch(() => {})
  }, [repoId])

  const addSon = () => setSons(s => [...s, { part_number: '', qty: 1, position: '' }])
  const updateSon = (i, field, val) => setSons(s => s.map((x, idx) => idx === i ? { ...x, [field]: val } : x))
  const removeSon = i => setSons(s => s.filter((_, idx) => idx !== i))

  const addFather = () => setFathers(f => [...f, { part_number: '', qty: 1, position: '' }])
  const updateFather = (i, field, val) => setFathers(f => f.map((x, idx) => idx === i ? { ...x, [field]: val } : x))
  const removeFather = i => setFathers(f => f.filter((_, idx) => idx !== i))

  const handleSubmit = async e => {
    e.preventDefault()
    if (!author.trim()) return setErr('Enter your name')
    if (!message.trim()) return setErr('Enter a commit message')
    if (isPart && fathers.length === 0) return setErr('A "Part" drawing must be linked to at least one parent assembly')
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

      const currentDocId = file.doc_id || result?.document_id
      const needsBom = (canHaveSons && sons.length > 0) || fathers.length > 0
      const docByPart = needsBom ? Object.fromEntries(allDocs.map(d => [d.part_number.toUpperCase(), d])) : {}

      // sons — assemblies and parts can have sons
      if (currentDocId && canHaveSons && sons.length > 0) {
        for (const son of sons) {
          const comp = docByPart[son.part_number.toUpperCase()]
          if (!comp) continue
          await addBomEntry(repoId, currentDocId, {
            component_id: comp.id,
            quantity: parseInt(son.qty) || 1,
            position: son.position || null,
            item_type: comp.doc_type === 'assembly' ? 'assembly' : 'part',
          }).catch(() => {})   // skip duplicates silently
        }
      }

      // fathers — current doc is the component, link it to its parent assemblies
      if (currentDocId && fathers.length > 0) {
        const currentItemType = isAssembly ? 'assembly' : 'part'
        for (const father of fathers) {
          const parentAssembly = docByPart[father.part_number.toUpperCase()]
          if (!parentAssembly || parentAssembly.doc_type !== 'assembly') continue
          await addBomEntry(repoId, parentAssembly.id, {
            component_id: currentDocId,
            quantity: parseInt(father.qty) || 1,
            position: father.position || null,
            item_type: currentItemType,
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
      padding: '14px 16px', background: 'var(--surface-2)',
      border: '1px solid var(--border-soft)', borderTop: 'none',
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
              <option value="part">Part</option>
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
      {/* ── Sons — component drawings inside this assembly or part ── */}
      {canHaveSons && (
        <div style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '10px 12px', background: 'var(--surface)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>Component drawings (sons)</span>
            <button type="button" onClick={addSon}
              style={{ fontSize: '12px', padding: '2px 10px', border: '1px solid var(--accent)', borderRadius: '4px', cursor: 'pointer', background: 'none', color: 'var(--accent)' }}>
              + Add
            </button>
          </div>
          {sons.length === 0 && (
            <p style={{ fontSize: '12px', color: 'var(--text-faint)', margin: 0 }}>No components yet — click + Add to link child drawings.</p>
          )}
          {sons.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: '6px', marginBottom: '6px', alignItems: 'center' }}>
              <input placeholder="Part number" value={s.part_number}
                onChange={e => updateSon(i, 'part_number', e.target.value)}
                list={`sons-list-${i}`} style={{ ...inputStyle, flex: 2 }} />
              <datalist id={`sons-list-${i}`}>
                {allDocs.map(d => <option key={d.id} value={d.part_number}>{d.title}</option>)}
              </datalist>
              <input placeholder="Qty" type="number" min="1" value={s.qty}
                onChange={e => updateSon(i, 'qty', e.target.value)} style={{ ...inputStyle, width: '56px' }} />
              <input placeholder="Pos" value={s.position}
                onChange={e => updateSon(i, 'position', e.target.value)} style={{ ...inputStyle, width: '56px' }} />
              <button type="button" onClick={() => removeSon(i)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: '16px', padding: '0 4px' }}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* ── Fathers — only shown when at least one assembly exists to link to ── */}
      {allAssemblies.length > 0 && (
        <div style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '10px 12px', background: 'var(--surface)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>Parent assemblies (fathers)</span>
            <button type="button" onClick={addFather}
              style={{ fontSize: '12px', padding: '2px 10px', border: '1px solid var(--accent)', borderRadius: '4px', cursor: 'pointer', background: 'none', color: 'var(--accent)' }}>
              + Add
            </button>
          </div>
          {fathers.length === 0 && (
            <p style={{ fontSize: '12px', color: 'var(--text-faint)', margin: 0 }}>No parents yet — click + Add to link this drawing to an assembly.</p>
          )}
          {fathers.map((f, i) => (
            <div key={i} style={{ display: 'flex', gap: '6px', marginBottom: '6px', alignItems: 'center' }}>
              <input placeholder="Assembly part number" value={f.part_number}
                onChange={e => updateFather(i, 'part_number', e.target.value)}
                list={`fathers-list-${i}`} style={{ ...inputStyle, flex: 2 }} />
              <datalist id={`fathers-list-${i}`}>
                {allAssemblies.map(d => <option key={d.id} value={d.part_number}>{d.title}</option>)}
              </datalist>
              <input placeholder="Qty" type="number" min="1" value={f.qty}
                onChange={e => updateFather(i, 'qty', e.target.value)} style={{ ...inputStyle, width: '56px' }} />
              <input placeholder="Pos" value={f.position}
                onChange={e => updateFather(i, 'position', e.target.value)} style={{ ...inputStyle, width: '56px' }} />
              <button type="button" onClick={() => removeFather(i)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', fontSize: '16px', padding: '0 4px' }}>✕</button>
            </div>
          ))}
        </div>
      )}

      {err && <p style={{ color: 'var(--danger)', margin: 0, fontSize: '13px' }}>{err}</p>}
      <button type="submit" disabled={loading} style={{ ...btnStyle, alignSelf: 'flex-start' }}>
        {loading ? 'Committing…' : 'Commit from disk'}
      </button>
    </form>
  )
}

const btnStyle = { padding: '5px 14px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }
const inputStyle = { padding: '7px', border: '1px solid var(--border)', borderRadius: '4px', fontSize: '13px', background: 'var(--surface)' }
