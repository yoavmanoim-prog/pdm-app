import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getRepo, getLog, listDocuments, listBranches, createBranch, getTree, validateTree, syncStatus, push, pull, getDiff } from '../api'
import WorkingDirectory from '../components/WorkingDirectory'
import { RepoProvider, useRepo } from '../context/RepoContext'

// Inner component — has access to RepoContext
function RepositoryInner() {
  const { repoId } = useParams()
  const { version, refresh } = useRepo()

  const [repo, setRepo]           = useState(null)
  const [tab, setTab]             = useState('commits')
  const [commits, setCommits]     = useState([])
  const [documents, setDocuments] = useState([])
  const [branches, setBranches]   = useState([])
  const [tree, setTree]           = useState([])
  const [validation, setValidation] = useState(null)
  const [sync, setSync]           = useState(null)
  const [loading, setLoading]     = useState(true)
  const [selectedDiff, setSelectedDiff] = useState(null)

  // re-runs whenever version increments — triggered by any action anywhere on the page
  useEffect(() => {
    Promise.all([
      getRepo(repoId),
      getLog(repoId),
      listDocuments(repoId),
      listBranches(repoId),
      getTree(repoId),
      validateTree(repoId),
      syncStatus(repoId),
    ]).then(([r, c, d, b, t, v, s]) => {
      setRepo(r); setCommits(c); setDocuments(d)
      setBranches(b); setTree(t); setValidation(v); setSync(s)
    }).finally(() => setLoading(false))
  }, [repoId, version])

  const handlePush = async () => {
    try { const r = await push(repoId); alert(`Pushed ${r.pushed} commits`); refresh() }
    catch (e) { alert(e.message) }
  }
  const handlePull = async () => {
    try { const r = await pull(repoId); alert(`Pulled ${r.pulled} commits`); refresh() }
    catch (e) { alert(e.message) }
  }

  if (loading) return <p>Loading…</p>
  if (!repo) return <p>Repository not found.</p>

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div>
          <Link to="/" style={{ color: '#888', fontSize: '13px' }}>← Repositories</Link>
          <h2 style={{ margin: '4px 0' }}>{repo.name}</h2>
          {repo.description && <p style={{ color: '#666', margin: 0 }}>{repo.description}</p>}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {sync && (
            <span style={{ fontSize: '12px', color: sync.status === 'synced' ? 'green' : '#e67e22' }}>
              ● {sync.status} {sync.ahead > 0 ? `(${sync.ahead} ahead)` : ''}{sync.behind > 0 ? `(${sync.behind} behind)` : ''}
            </span>
          )}
          <button onClick={handlePush} style={btnSmall}>Push</button>
          <button onClick={handlePull} style={btnSmall}>Pull</button>
          <Link to={`/repos/${repoId}/upload`} style={{ ...btnSmall, textDecoration: 'none' }}>+ Commit</Link>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid #eee', marginBottom: '20px' }}>
        {['commits', 'documents', 'branches', 'tree', 'validate', 'working dir'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 18px', border: 'none', background: 'none', cursor: 'pointer', fontWeight: tab === t ? 'bold' : 'normal', borderBottom: tab === t ? '2px solid #1a1a2e' : '2px solid transparent', marginBottom: '-2px' }}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Commits tab */}
      {tab === 'commits' && (
        <div>
          {commits.length === 0 && <p style={{ color: '#888' }}>No commits yet.</p>}
          {commits.map(c => (
            <div key={c.id} style={rowStyle}>
              <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px', fontSize: '13px' }}>{c.short_hash}</code>
              <span style={{ marginLeft: '12px', flex: 1 }}>{c.message}</span>
              <span style={{ color: '#888', fontSize: '12px' }}>{c.author} · {new Date(c.timestamp).toLocaleString()}</span>
              {c.files?.length > 0 && (
                <button onClick={() => setSelectedDiff(selectedDiff === c.short_hash ? null : c.short_hash)}
                  style={{ ...btnSmall, marginLeft: '8px' }}>
                  {selectedDiff === c.short_hash ? 'Hide' : 'Diff'}
                </button>
              )}
              {selectedDiff === c.short_hash && <DiffPanel repoId={repoId} hash={c.short_hash} />}
            </div>
          ))}
        </div>
      )}

      {/* Documents tab */}
      {tab === 'documents' && (
        <div>
          <div style={{ marginBottom: '12px' }}>
            <Link to={`/repos/${repoId}/upload`} style={{ ...btnSmall, textDecoration: 'none' }}>+ Upload Drawing</Link>
          </div>
          {documents.length === 0 && <p style={{ color: '#888' }}>No documents yet.</p>}
          {documents.map(d => (
            <Link key={d.id} to={`/repos/${repoId}/documents/${d.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
              <div style={{ ...rowStyle, cursor: 'pointer' }}>
                <code style={{ fontSize: '13px', minWidth: '120px' }}>{d.part_number}</code>
                <span style={{ flex: 1, marginLeft: '12px' }}>{d.title}</span>
                <span style={{ fontSize: '12px', color: '#888', background: '#f0f0f0', padding: '2px 8px', borderRadius: '3px' }}>{d.doc_type}</span>
                <span style={{ fontSize: '11px', color: '#aaa', marginLeft: '8px' }}>View →</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Branches tab */}
      {tab === 'branches' && <BranchesTab repoId={repoId} branches={branches} />}

      {/* Tree tab */}
      {tab === 'tree' && (
        <div>
          {tree.length === 0 && <p style={{ color: '#888' }}>No product tree yet.</p>}
          {tree.map(node => <TreeNode key={node.id} node={node} depth={0} />)}
        </div>
      )}

      {/* Working Dir tab */}
      {tab === 'working dir' && <WorkingDirectory repoId={repoId} />}

      {/* Validate tab */}
      {tab === 'validate' && validation && (
        <div>
          <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
            <Stat label="Total" value={validation.total} />
            <Stat label="Released" value={validation.released} color="green" />
            <Stat label="Unreleased" value={validation.unreleased} color="#e67e22" />
            <Stat label="No Drawing" value={validation.missing_drawing} color="red" />
          </div>
          {validation.documents.map(d => (
            <div key={d.document_id} style={{ ...rowStyle, opacity: d.has_drawing ? 1 : 0.6 }}>
              <code style={{ fontSize: '13px', minWidth: '120px' }}>{d.part_number}</code>
              <span style={{ flex: 1, marginLeft: '12px' }}>{d.title}</span>
              {d.current_revision
                ? <span style={{ color: 'green', fontSize: '12px', marginRight: '8px' }}>Rev {d.current_revision}</span>
                : <span style={{ color: '#888', fontSize: '12px', marginRight: '8px' }}>Unreleased</span>}
              {!d.has_drawing && <span style={{ color: 'red', fontSize: '12px' }}>⚠ No drawing</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Branches tab extracted so it can show a create-branch form with refresh on submit
function BranchesTab({ repoId, branches }) {
  const { refresh } = useRepo()
  const [name, setName]     = useState('')
  const [author, setAuthor] = useState('')
  const [creating, setCreating] = useState(false)
  const [err, setErr]       = useState(null)

  const handleCreate = async e => {
    e.preventDefault()
    if (!name.trim() || !author.trim()) return setErr('Enter branch name and your name')
    setCreating(true); setErr(null)
    try {
      await createBranch(repoId, { name, created_by: author })
      setName(''); setAuthor('')
      refresh()  // all tabs update instantly
    } catch (e) { setErr(e.message) }
    finally { setCreating(false) }
  }

  return (
    <div>
      <form onSubmit={handleCreate} style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <input required placeholder="Branch name" value={name} onChange={e => setName(e.target.value)}
          style={inputStyle} />
        <input required placeholder="Your name" value={author} onChange={e => setAuthor(e.target.value)}
          style={inputStyle} />
        <button type="submit" disabled={creating} style={btnSmall}>
          {creating ? 'Creating…' : '+ New Branch'}
        </button>
        {err && <span style={{ color: 'red', fontSize: '13px', alignSelf: 'center' }}>{err}</span>}
      </form>

      {branches.length === 0 && <p style={{ color: '#888' }}>No branches yet.</p>}
      {branches.map(b => (
        <div key={b.id} style={rowStyle}>
          <span style={{ flex: 1 }}>{b.name}</span>
          <span style={{ fontSize: '12px', marginRight: '12px', color: b.status === 'open' ? 'green' : '#888' }}>{b.status}</span>
          <span style={{ fontSize: '12px', color: '#888' }}>by {b.created_by} · {new Date(b.created_at).toLocaleDateString()}</span>
          {b.status === 'open' && (
            <Link to={`/repos/${repoId}/branches/${b.id}`}
              style={{ ...btnSmall, textDecoration: 'none', marginLeft: '8px' }}>
              Merge Request
            </Link>
          )}
        </div>
      ))}
    </div>
  )
}

// exported wrapper — provides the context
export default function Repository() {
  return (
    <RepoProvider>
      <RepositoryInner />
    </RepoProvider>
  )
}

function TreeNode({ node, depth }) {
  return (
    <div style={{ marginLeft: depth * 24, borderLeft: depth > 0 ? '2px solid #eee' : 'none', paddingLeft: depth > 0 ? 12 : 0, marginBottom: '4px' }}>
      <div style={{ ...rowStyle, background: '#fafafa' }}>
        <code style={{ fontSize: '13px', minWidth: '120px' }}>{node.part_number}</code>
        <span style={{ flex: 1, marginLeft: '12px' }}>{node.title}</span>
        <span style={{ fontSize: '11px', color: '#888', marginRight: '8px' }}>{node.doc_type}</span>
        {node.revision
          ? <span style={{ color: 'green', fontSize: '12px' }}>Rev {node.revision}</span>
          : <span style={{ color: '#aaa', fontSize: '12px' }}>Unreleased</span>}
        {node.quantity && <span style={{ fontSize: '12px', color: '#666', marginLeft: '8px' }}>×{node.quantity}</span>}
      </div>
      {node.children?.map(child => <TreeNode key={child.id} node={child} depth={depth + 1} />)}
    </div>
  )
}

function Stat({ label, value, color = '#333' }) {
  return (
    <div style={{ textAlign: 'center', padding: '12px 20px', background: '#f5f5f5', borderRadius: '6px' }}>
      <div style={{ fontSize: '24px', fontWeight: 'bold', color }}>{value}</div>
      <div style={{ fontSize: '12px', color: '#888' }}>{label}</div>
    </div>
  )
}

function DiffPanel({ repoId, hash }) {
  const [diff, setDiff] = useState(null)
  useEffect(() => {
    getDiff(repoId, hash).then(setDiff).catch(() => {})
  }, [repoId, hash])
  if (!diff) return <div style={{ padding: '8px', color: '#888' }}>Loading diff…</div>
  return (
    <div style={{ width: '100%', marginTop: '8px', padding: '12px', background: '#f9f9f9', borderRadius: '4px' }}>
      {diff.files.map((f, i) => (
        <div key={i} style={{ marginBottom: '8px' }}>
          <strong style={{ fontSize: '13px' }}>{f.part_number} ({f.change_type})</strong>
          <div style={{ display: 'flex', gap: '12px', marginTop: '6px' }}>
            {f.previous_pdf_url && <a href={f.previous_pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: '12px', color: '#666' }}>Previous PDF ↗</a>}
            {f.current_pdf_url && <a href={f.current_pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: '12px', color: '#1a1a2e' }}>Current PDF ↗</a>}
          </div>
        </div>
      ))}
    </div>
  )
}

const btnSmall = { padding: '5px 12px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }
const rowStyle = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', padding: '10px 12px', border: '1px solid #eee', borderRadius: '4px', marginBottom: '6px' }
const inputStyle = { padding: '6px 10px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '13px' }
