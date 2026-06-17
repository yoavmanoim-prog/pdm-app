import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getRepo, getLog, listDocuments, listBranches, createBranch, getTree, validateTree, syncStatus, push, pull, getDiff, editDocument, getDocumentLatestCommit, getDocumentBom, amendCommit, removeBomEntry, addBomEntry, linkRepo, listRemoteRepos, getRepoSettings, updateRepoSettings, createReleaseRequest, listReleaseRequests, approveReleaseRequest, denyReleaseRequest } from '../api'
import WorkingDirectory from '../components/WorkingDirectory'
import { RepoProvider, useRepo } from '../context/RepoContext'
import { useMode } from '../context/ModeContext'

// Friendly labels for the sync status pill
const SYNC_LABELS = {
  synced: 'synced',
  remote_unreachable: 'remote unreachable',
  remote_misconfigured: 'remote URL invalid (missing /api?)',
}

// Inner component — has access to RepoContext
function RepositoryInner() {
  const { repoId } = useParams()
  const { version, refresh } = useRepo()
  const { mode, vaultUrl } = useMode()
  const navigate = useNavigate()

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
  const [linkingRemote, setLinkingRemote] = useState(false)
  const [remoteUrlInput, setRemoteUrlInput] = useState('')
  const [remoteRepos, setRemoteRepos] = useState(null)   // null = not fetched yet
  const [fetchingRepos, setFetchingRepos] = useState(false)
  const [linkErr, setLinkErr] = useState(null)

  // re-runs whenever version increments — triggered by any action anywhere on the page
  useEffect(() => {
    // load repo first — if it 404s we show not-found, no point fetching the rest
    getRepo(repoId).then(r => {
      setRepo(r)
      // load secondary data independently so a single failure doesn't blank the page
      Promise.allSettled([
        getLog(repoId),
        listDocuments(repoId),
        listBranches(repoId),
        getTree(repoId),
        validateTree(repoId),
        syncStatus(repoId),
      ]).then(([c, d, b, t, v, s]) => {
        if (c.status === 'fulfilled') setCommits(c.value)
        if (d.status === 'fulfilled') setDocuments(d.value)
        if (b.status === 'fulfilled') setBranches(b.value)
        if (t.status === 'fulfilled') setTree(t.value)
        if (v.status === 'fulfilled') setValidation(v.value)
        if (s.status === 'fulfilled') setSync(s.value)
      })
    }).catch(() => setRepo(null)).finally(() => setLoading(false))
  }, [repoId, version])

  const handlePush = async () => {
    try {
      const r = await push(repoId)
      alert(`Pushed ${r.pushed} commits`)
      refresh()
    } catch (e) {
      alert(e.message)
      if (e.message.includes('Remote repository was deleted')) refresh()
    }
  }
  const handlePull = async () => {
    try {
      const r = await pull(repoId)
      alert(`Pulled ${r.pulled} commits`)
      refresh()
    } catch (e) {
      alert(e.message)
      if (e.message.includes('Remote repository was deleted')) refresh()
    }
  }
  const openLinkDialog = () => {
    setRemoteUrlInput(repo?.remote_url || '')
    setRemoteRepos(null)
    setLinkErr(null)
    setLinkingRemote(true)
  }
  // step 1: look up the repos on the entered remote vault
  const handleFetchRemoteRepos = async () => {
    const url = remoteUrlInput.trim()
    if (!url) return setLinkErr('Enter the remote vault URL first')
    setFetchingRepos(true); setLinkErr(null)
    try {
      setRemoteRepos(await listRemoteRepos(url))
    } catch (e) { setLinkErr(e.message); setRemoteRepos(null) }
    finally { setFetchingRepos(false) }
  }
  // step 2: link to a chosen remote repo (remoteRepoId null = create a new one)
  const handleLinkRemote = async (remoteRepoId) => {
    try {
      await linkRepo(repoId, remoteUrlInput.trim(), remoteRepoId)
      setLinkingRemote(false)
      refresh()
    } catch (e) { setLinkErr(e.message) }
  }

  if (loading) return <p>Loading…</p>
  if (!repo) return (
    <div style={{ padding: '20px' }}>
      <p style={{ color: '#888' }}>Repository not found on this vault.</p>
      <button onClick={() => navigate('/')} style={{ padding: '6px 14px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
        ← Back to repositories
      </button>
    </div>
  )

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div>
          <Link to="/" style={{ color: '#888', fontSize: '13px' }}>← Repositories</Link>
          <h2 style={{ margin: '4px 0' }}>{repo.name}</h2>
          {repo.description && <p style={{ color: '#666', margin: 0 }}>{repo.description}</p>}
          {mode === 'remote' && vaultUrl && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '6px' }}>
              <span style={{ fontSize: '11px', color: '#888' }}>Vault URL:</span>
              <code style={{ fontSize: '11px', background: '#f0f0f0', padding: '2px 8px', borderRadius: '10px', color: '#444' }}>
                {vaultUrl}
              </code>
              <button
                onClick={() => navigator.clipboard.writeText(vaultUrl).then(() => alert('Copied!'))}
                title="Copy to clipboard"
                style={{ background: 'none', border: '1px solid #ddd', borderRadius: '4px', padding: '1px 8px', fontSize: '11px', cursor: 'pointer', color: '#666' }}
              >
                Copy
              </button>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          {sync && sync.status !== 'remote_deleted' && (
            <span
              style={{ fontSize: '12px', color: sync.status === 'synced' ? 'green' : '#e67e22' }}
              title={sync.status === 'remote_misconfigured' ? 'A server answered but it is not a vault — the remote URL is likely missing /api' : undefined}
            >
              ● {SYNC_LABELS[sync.status] || sync.status} {sync.ahead > 0 ? `(${sync.ahead} ahead)` : ''}{sync.behind > 0 ? `(${sync.behind} behind)` : ''}
            </span>
          )}
          {sync?.status === 'remote_deleted' && (
            <span style={{ fontSize: '12px', color: '#c0392b' }}>● remote deleted — link cleared</span>
          )}
          {mode === 'local' && repo && (
            repo.remote_url ? (
              <span style={{ fontSize: '11px', color: '#888', background: '#f0f0f0', padding: '2px 8px', borderRadius: '10px', cursor: 'pointer' }}
                title="Click to change the remote link"
                onClick={openLinkDialog}>
                ⇄ {repo.remote_url.replace(/^https?:\/\//, '')}
              </span>
            ) : (
              <button onClick={openLinkDialog} style={{ ...btnSmall, background: '#e8e8f0', color: '#444' }}>
                Link Remote
              </button>
            )
          )}
          <button onClick={handlePush} style={btnSmall}>Push</button>
          <button onClick={handlePull} style={btnSmall}>Pull</button>
          <Link to={`/repos/${repoId}/upload`} style={{ ...btnSmall, textDecoration: 'none' }}>+ Commit</Link>
        </div>
      </div>

      {linkingRemote && (
        <div style={{ background: '#f5f5f5', border: '1px solid #ddd', borderRadius: '6px', padding: '12px', marginBottom: '16px' }}>
          {/* Step 1 — enter the remote vault URL and look up its repos */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: '#555', whiteSpace: 'nowrap' }}>Remote vault URL:</span>
            <input
              autoFocus
              value={remoteUrlInput}
              onChange={e => { setRemoteUrlInput(e.target.value); setRemoteRepos(null) }}
              placeholder="https://your-remote-vault.example.com/api"
              style={{ flex: 1, padding: '6px 10px', border: '1px solid #ccc', borderRadius: '4px', fontSize: '13px' }}
              onKeyDown={e => { if (e.key === 'Enter') handleFetchRemoteRepos(); if (e.key === 'Escape') setLinkingRemote(false) }}
            />
            <button onClick={handleFetchRemoteRepos} disabled={fetchingRepos} style={btnSmall}>
              {fetchingRepos ? 'Looking…' : 'Find repos'}
            </button>
            <button onClick={() => setLinkingRemote(false)} style={{ ...btnSmall, background: '#e8e8f0', color: '#444' }}>Cancel</button>
          </div>
          <div style={{ fontSize: '11px', color: '#888', marginTop: '6px' }}>
            <code>/api</code> is added automatically if needed (CloudFront serves the API under <code>/api</code>).
          </div>

          {linkErr && <div style={{ fontSize: '12px', color: '#c0392b', marginTop: '8px' }}>{linkErr}</div>}

          {/* Step 2 — choose which remote repo to connect to, or create a new one */}
          {remoteRepos && (
            <div style={{ marginTop: '12px', borderTop: '1px solid #ddd', paddingTop: '10px' }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#333', marginBottom: '6px' }}>
                Connect this repo to:
              </div>
              {remoteRepos.length === 0 && (
                <div style={{ fontSize: '12px', color: '#888', marginBottom: '8px' }}>No repos on the remote yet.</div>
              )}
              {remoteRepos.map(rr => (
                <div key={rr.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 8px', border: '1px solid #e5e5e5', borderRadius: '4px', marginBottom: '6px', background: '#fff' }}>
                  <span style={{ fontSize: '13px' }}>
                    {rr.name} <span style={{ color: '#aaa', fontSize: '11px' }}>· {rr.document_count} docs · {rr.id.slice(0, 8)}</span>
                  </span>
                  <button onClick={() => handleLinkRemote(rr.id)} style={btnSmall}>Connect</button>
                </div>
              ))}
              <button
                onClick={() => handleLinkRemote(null)}
                style={{ ...btnSmall, background: '#e8e8f0', color: '#444', marginTop: '4px' }}
                title="Create a new repository on the remote from this local repo"
              >
                + Create new on the remote
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid #eee', marginBottom: '20px' }}>
        {['commits', 'documents', 'branches', 'tree', 'validate', ...(mode === 'remote' ? ['releases', 'settings'] : ['working dir', 'settings'])].map(t => (
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
              {/* show drawing part numbers instead of hash */}
              <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                {c.files?.length > 0
                  ? c.files.map(f => (
                    <code key={f.id} style={{ background: '#e8f0fe', color: '#1a1a2e', padding: '2px 7px', borderRadius: '3px', fontSize: '12px' }}>
                      {f.part_number ? f.part_number.split(' ')[0] : f.document_id.slice(0, 8)}
                    </code>
                  ))
                  : <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '3px', fontSize: '12px', color: '#aaa' }}>{c.short_hash}</code>
                }
              </div>
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
        <DocumentsTab repoId={repoId} documents={documents} validation={validation} />
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

      {/* Working Dir tab — local vault only */}
      {tab === 'working dir' && mode === 'local' && <WorkingDirectory repoId={repoId} />}

      {tab === 'settings' && <SettingsTab repoId={repoId} mode={mode} />}

      {/* Validate tab */}
      {tab === 'validate' && validation && (
        <ValidateTab validation={validation} />
      )}

      {/* Releases tab — remote vault only */}
      {tab === 'releases' && mode === 'remote' && (
        <ReleasesTab repoId={repoId} />
      )}
    </div>
  )
}

function BranchesTab({ repoId, branches }) {
  const { refresh } = useRepo()
  const [name, setName]         = useState('')
  const [author, setAuthor]     = useState('')
  const [creating, setCreating] = useState(false)
  const [err, setErr]           = useState(null)
  const [expanded, setExpanded] = useState({})      // branchId → boolean
  const [commits, setCommits]   = useState({})      // branchId → commit[]

  const toggle = async (id) => {
    const next = !expanded[id]
    setExpanded(e => ({ ...e, [id]: next }))
    if (next && !commits[id]) {
      const log = await getLog(repoId, 50, id)
      setCommits(c => ({ ...c, [id]: log }))
    }
  }

  const handleCreate = async e => {
    e.preventDefault()
    if (!name.trim() || !author.trim()) return setErr('Enter branch name and your name')
    setCreating(true); setErr(null)
    try {
      await createBranch(repoId, { name, created_by: author })
      setName(''); setAuthor('')
      refresh()
    } catch (e) { setErr(e.message) }
    finally { setCreating(false) }
  }

  // default "main" branch is always at the top — commits with no branch_id
  const allBranches = [
    { id: 'main', name: 'main', status: 'default', created_by: 'system', created_at: null },
    ...branches,
  ]

  return (
    <div>
      <form onSubmit={handleCreate} style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <input required placeholder="Branch name" value={name} onChange={e => setName(e.target.value)} style={inputStyle} />
        <input required placeholder="Your name" value={author} onChange={e => setAuthor(e.target.value)} style={inputStyle} />
        <button type="submit" disabled={creating} style={btnSmall}>{creating ? 'Creating…' : '+ New Branch'}</button>
        {err && <span style={{ color: 'red', fontSize: '13px', alignSelf: 'center' }}>{err}</span>}
      </form>

      {allBranches.map(b => (
        <div key={b.id} style={{ marginBottom: '4px' }}>
          {/* branch row */}
          <div style={{ ...rowStyle, cursor: 'pointer' }} onClick={() => toggle(b.id)}>
            <span style={{ fontSize: '14px', marginRight: '8px', color: '#999', transition: 'transform 0.15s', display: 'inline-block', transform: expanded[b.id] ? 'rotate(90deg)' : 'rotate(0deg)' }}>▶</span>
            <span style={{ flex: 1, fontWeight: b.id === 'main' ? 600 : 400 }}>{b.name}</span>
            <span style={{ fontSize: '12px', marginRight: '12px', color: b.id === 'main' ? '#1a1a2e' : b.status === 'open' ? 'green' : '#888' }}>
              {b.id === 'main' ? 'default' : b.status}
            </span>
            {b.created_at && <span style={{ fontSize: '12px', color: '#aaa' }}>by {b.created_by} · {new Date(b.created_at).toLocaleDateString()}</span>}
            {b.status === 'open' && (
              <Link to={`/repos/${repoId}/branches/${b.id}`} onClick={e => e.stopPropagation()}
                style={{ ...btnSmall, textDecoration: 'none', marginLeft: '8px' }}>
                Merge Request
              </Link>
            )}
          </div>

          {/* commit list — shown when expanded */}
          {expanded[b.id] && (
            <div style={{ marginLeft: '28px', borderLeft: '2px solid #eee', paddingLeft: '12px', marginBottom: '8px' }}>
              {!commits[b.id] && <p style={{ color: '#aaa', fontSize: '13px', margin: '6px 0' }}>Loading…</p>}
              {commits[b.id]?.length === 0 && <p style={{ color: '#aaa', fontSize: '13px', margin: '6px 0' }}>No commits on this branch yet.</p>}
              {commits[b.id]?.map(c => (
                <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 8px', borderRadius: '4px', marginBottom: '3px', background: '#fafafa', fontSize: '13px' }}>
                  {c.files?.length > 0
                    ? c.files.map(f => (
                      <code key={f.id} style={{ background: '#e8f0fe', color: '#1a1a2e', padding: '1px 6px', borderRadius: '3px', fontSize: '12px' }}>
                        {f.part_number ? f.part_number.split(' ')[0] : f.document_id.slice(0, 8)}
                      </code>
                    ))
                    : <code style={{ background: '#f0f0f0', padding: '1px 6px', borderRadius: '3px', fontSize: '12px', color: '#aaa' }}>{c.short_hash}</code>
                  }
                  <span style={{ flex: 1 }}>{c.message}</span>
                  <span style={{ color: '#aaa', fontSize: '11px' }}>{c.author} · {new Date(c.timestamp).toLocaleDateString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function DocumentsTab({ repoId, documents, validation }) {
  const { refresh } = useRepo()
  const { mode } = useMode()
  const [editing, setEditing] = useState(null)
  const [requesting, setRequesting] = useState(null)   // doc id with open release request form

  const revByDocId = {}
  if (validation) {
    for (const vd of validation.documents) revByDocId[vd.document_id] = vd
  }

  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <Link to={`/repos/${repoId}/upload`} style={{ ...btnSmall, textDecoration: 'none' }}>+ Upload Drawing</Link>
      </div>
      {documents.length === 0 && <p style={{ color: '#888' }}>No documents yet.</p>}
      {documents.map(d => {
        const vd = revByDocId[d.id]
        return (
          <div key={d.id}>
          {/* document row — always visible */}
          <div style={{ position: 'relative' }}>
            <Link to={`/repos/${repoId}/documents/${d.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
              <div style={{
                ...rowStyle,
                cursor: 'pointer',
                paddingRight: '60px',
                borderRadius: editing === d.id ? '4px 4px 0 0' : '4px',
                marginBottom: editing === d.id ? 0 : '6px',
                borderBottom: editing === d.id ? 'none' : '1px solid #eee',
              }}>
                <code style={{ fontSize: '13px', minWidth: '120px' }}>{d.part_number}</code>
                <span style={{ flex: 1, marginLeft: '12px' }}>{d.title}</span>
                {vd?.revision
                  ? <span style={{ fontSize: '12px', color: 'green', marginRight: '6px' }}>Rev {vd.revision}</span>
                  : <span style={{ fontSize: '12px', color: '#aaa', marginRight: '6px' }}>Unreleased</span>}
                {vd?.revision_mismatch && (
                  <span title={`File says REV-${vd.title_revision}, vault assigned Rev ${vd.revision}`}
                    style={{ fontSize: '11px', color: '#c0392b', background: '#fdecea', padding: '2px 6px', borderRadius: '3px', marginRight: '6px', cursor: 'help' }}>
                    ⚠ Rev mismatch
                  </span>
                )}
                <span style={{ fontSize: '12px', color: '#888', background: '#f0f0f0', padding: '2px 8px', borderRadius: '3px' }}>{d.doc_type}</span>
                <span style={{ fontSize: '11px', color: '#aaa', marginLeft: '8px' }}>View →</span>
              </div>
            </Link>
            <div style={{ position: 'absolute', top: '50%', right: '8px', transform: 'translateY(-50%)', display: 'flex', gap: '4px' }}>
              {mode === 'remote' && vd?.has_drawing && (
                <button
                  onClick={e => { e.preventDefault(); setRequesting(requesting === d.id ? null : d.id); setEditing(null) }}
                  style={{ background: requesting === d.id ? '#1a5c2e' : 'none', color: requesting === d.id ? '#fff' : '#1a5c2e', border: '1px solid #1a5c2e', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: '11px' }}>
                  {requesting === d.id ? 'Cancel' : '↑ Release'}
                </button>
              )}
              {mode === 'local' && (
                <button
                  onClick={e => { e.preventDefault(); setEditing(editing === d.id ? null : d.id); setRequesting(null) }}
                  style={{ background: editing === d.id ? '#1a1a2e' : 'none', color: editing === d.id ? '#fff' : '#888', border: '1px solid #ddd', borderRadius: '4px', padding: '2px 8px', cursor: 'pointer', fontSize: '11px' }}>
                  {editing === d.id ? 'Close' : 'Edit'}
                </button>
              )}
            </div>
          </div>

          {/* release request form */}
          {requesting === d.id && (
            <ReleaseRequestForm repoId={repoId} doc={d} vd={vd}
              onDone={() => { setRequesting(null); refresh() }}
              onCancel={() => setRequesting(null)} />
          )}

          {/* full edit form */}
          {editing === d.id && (
            <EditDocumentForm
              repoId={repoId}
              doc={d}
              allDocuments={documents}
              onDone={() => { setEditing(null); refresh() }}
              onCancel={() => setEditing(null)}
            />
          )}
          </div>
        )
      })}
    </div>
  )
}

function EditDocumentForm({ repoId, doc, allDocuments, onDone, onCancel }) {
  const [form, setForm]             = useState({ part_number: doc.part_number, title: doc.title, doc_type: doc.doc_type, author: '', message: '' })
  const [commitHash, setCommitHash] = useState(null)
  const [sons, setSons]             = useState([])
  const [origSonIds, setOrigSonIds] = useState([])
  const [loading, setLoading]       = useState(true)
  const [loadError, setLoadError]   = useState(null)   // load-time error — blocks the form entirely
  const [saving, setSaving]         = useState(false)
  const [saveErr, setSaveErr]       = useState(null)   // save-time error

  const otherDocs = allDocuments.filter(d => d.id !== doc.id)

  useEffect(() => {
    let mounted = true   // prevent state updates after unmount
    Promise.all([
      getDocumentLatestCommit(repoId, doc.id),
      getDocumentBom(repoId, doc.id),
    ]).then(([latest, bom]) => {
      if (!mounted) return
      if (latest?.commit_hash) {
        // only overwrite if the user hasn't started typing yet
        setForm(f => ({
          ...f,
          author:  f.author  === '' ? latest.author  : f.author,
          message: f.message === '' ? latest.message : f.message,
        }))
        setCommitHash(latest.commit_hash)
      }
      const loaded = bom.map(e => ({ id: e.id, part_number: e.part_number || '', qty: e.quantity, position: e.position || '' }))
      setSons(loaded)
      setOrigSonIds(loaded.map(s => s.id))
    }).catch(e => {
      if (mounted) setLoadError(e.message)
    }).finally(() => {
      if (mounted) setLoading(false)
    })
    return () => { mounted = false }
  }, [repoId, doc.id])

  const isAssembly = form.doc_type === 'assembly'
  const canHaveSons = form.doc_type === 'assembly' || form.doc_type === 'part'

  const addSon = () => setSons(s => [...s, { id: null, part_number: '', qty: 1, position: '' }])
  const updateSon = (i, field, val) => setSons(s => s.map((x, idx) => idx === i ? { ...x, [field]: val } : x))
  const removeSon = i => setSons(s => s.filter((_, idx) => idx !== i))

  const handleSubmit = async e => {
    e.preventDefault()
    if (commitHash && !form.author.trim()) return setSaveErr('Author is required')
    if (commitHash && !form.message.trim()) return setSaveErr('Commit message is required')
    setSaving(true); setSaveErr(null)
    try {
      // 1. update document metadata
      await editDocument(repoId, doc.id, { part_number: form.part_number, title: form.title, doc_type: form.doc_type })

      // 2. amend the latest commit's author and message (skipped if doc has no commits)
      if (commitHash) {
        await amendCommit(repoId, commitHash, { author: form.author, message: form.message })
      }

      // 3. reconcile BOM — swallow 404s on removal (concurrent deletes), bubble real errors
      const currentIds = sons.filter(s => s.id).map(s => s.id)
      const removed = origSonIds.filter(id => !currentIds.includes(id))
      await Promise.all(removed.map(id => removeBomEntry(repoId, id).catch(() => {})))

      const docByPart = Object.fromEntries(otherDocs.map(d => [d.part_number.toUpperCase(), d]))
      for (const son of sons.filter(s => !s.id && s.part_number.trim())) {
        const comp = docByPart[son.part_number.toUpperCase()]
        if (!comp) continue
        await addBomEntry(repoId, doc.id, {
          component_id: comp.id,
          quantity: parseInt(son.qty) || 1,
          position: son.position || null,
          item_type: comp.doc_type === 'assembly' ? 'assembly' : 'part',
        }).catch(e => {
          // silently skip duplicate entries (409), surface all other failures
          if (!e.message.includes('already in this assembly')) throw e
        })
      }

      onDone()
    } catch (e) {
      setSaveErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div style={{ padding: '12px 16px', background: '#f9f9f9', border: '1px solid #eee', borderTop: 'none', borderRadius: '0 0 4px 4px', marginBottom: '6px', fontSize: '13px', color: '#888' }}>
      Loading…
    </div>
  )

  // if the load itself failed, block the form entirely — don't let users save against incomplete state
  if (loadError) return (
    <div style={{ padding: '12px 16px', background: '#fff3cd', border: '1px solid #eee', borderTop: 'none', borderRadius: '0 0 4px 4px', marginBottom: '6px', fontSize: '13px', color: '#856404', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span>Failed to load: {loadError}</span>
      <button type="button" onClick={onCancel} style={{ ...btnSmall, background: '#aaa' }}>Close</button>
    </div>
  )

  return (
    <form onSubmit={handleSubmit} style={{ padding: '14px 16px', background: '#f9f9f9', border: '1px solid #eee', borderTop: 'none', borderRadius: '0 0 4px 4px', marginBottom: '6px', display: 'flex', flexDirection: 'column', gap: '8px' }}>

      {/* Document metadata */}
      <div style={{ display: 'flex', gap: '8px' }}>
        <input value={form.part_number} onChange={e => setForm(f => ({ ...f, part_number: e.target.value }))}
          style={{ ...inputStyle, flex: 1 }} placeholder="Part number" required />
        <select value={form.doc_type} onChange={e => setForm(f => ({ ...f, doc_type: e.target.value }))} style={inputStyle}>
          <option value="detail">Detail</option>
          <option value="assembly">Assembly</option>
          <option value="part">Part</option>
        </select>
      </div>
      <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
        style={inputStyle} placeholder="Title" required />

      {/* Commit attribution — only shown when there is a prior commit to amend */}
      {commitHash && (
        <>
          <input value={form.author} onChange={e => setForm(f => ({ ...f, author: e.target.value }))}
            style={inputStyle} placeholder="Author *" required />
          <input value={form.message} onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
            style={inputStyle} placeholder="Commit message *" required />
        </>
      )}

      {/* BOM sons — for assemblies and parts */}
      {canHaveSons && (
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
              <input placeholder="Part number" value={s.part_number}
                onChange={e => updateSon(i, 'part_number', e.target.value)}
                list={`edit-docs-list-${i}`}
                style={{ ...inputStyle, flex: 2 }}
                readOnly={!!s.id}
              />
              <datalist id={`edit-docs-list-${i}`}>
                {otherDocs.map(d => <option key={d.id} value={d.part_number}>{d.title}</option>)}
              </datalist>
              <input placeholder="Qty" type="number" min="1" value={s.qty}
                onChange={e => updateSon(i, 'qty', e.target.value)}
                style={{ ...inputStyle, width: '56px' }} />
              <input placeholder="Pos" value={s.position}
                onChange={e => updateSon(i, 'position', e.target.value)}
                style={{ ...inputStyle, width: '56px' }} />
              <button type="button" onClick={() => removeSon(i)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#aaa', fontSize: '16px', padding: '0 4px' }}>✕</button>
            </div>
          ))}
        </div>
      )}

      {saveErr && <p style={{ color: 'red', margin: 0, fontSize: '13px' }}>{saveErr}</p>}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button type="submit" disabled={saving} style={btnSmall}>{saving ? 'Saving…' : 'Save'}</button>
        <button type="button" onClick={onCancel} style={{ ...btnSmall, background: '#aaa' }}>Cancel</button>
      </div>
    </form>
  )
}

function ReleaseRequestForm({ repoId, doc, vd, onDone, onCancel }) {
  const [requestedBy, setRequestedBy] = useState('')
  const [changeNote, setChangeNote]   = useState('')
  const [loading, setLoading]         = useState(false)
  const [err, setErr]                 = useState(null)

  // must mirror REVISION_SEQUENCE from the backend (A-P, skipping I and O)
  const REV_SEQ = 'ABCDEFGHJKLMNP'.split('')
  const currentIdx = vd?.revision ? REV_SEQ.indexOf(vd.revision.toUpperCase()) : -1
  const proposedCode = currentIdx >= 0 && currentIdx + 1 < REV_SEQ.length
    ? REV_SEQ[currentIdx + 1]
    : 'A'
  const needsChangeNote = proposedCode !== 'A'

  const handleSubmit = async e => {
    e.preventDefault()
    if (!requestedBy.trim()) return setErr('Enter your name')
    if (needsChangeNote && !changeNote.trim()) return setErr('Change note required for Rev ' + proposedCode)
    setLoading(true); setErr(null)
    try {
      await createReleaseRequest(repoId, doc.id, { requested_by: requestedBy, change_note: changeNote || null })
      onDone()
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} style={{ padding: '12px 16px', background: '#f0faf4', border: '1px solid #b7e4c7', borderTop: 'none', borderRadius: '0 0 4px 4px', marginBottom: '6px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{ fontSize: '13px', color: '#1a5c2e', fontWeight: 600 }}>
        Request release of <strong>{doc.part_number}</strong> as <strong>Rev {proposedCode}</strong>
        {vd?.revision && <span style={{ fontWeight: 400, color: '#666' }}> (currently Rev {vd.revision})</span>}
      </div>
      <input required placeholder="Your name" value={requestedBy}
        onChange={e => setRequestedBy(e.target.value)} style={inputStyle} />
      <textarea
        placeholder={needsChangeNote ? 'Change note (required for Rev ' + proposedCode + ')' : 'Change note (optional for Rev A)'}
        value={changeNote} onChange={e => setChangeNote(e.target.value)}
        rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
      {err && <p style={{ color: 'red', margin: 0, fontSize: '13px' }}>{err}</p>}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button type="submit" disabled={loading} style={{ ...btnSmall, background: '#1a5c2e' }}>
          {loading ? 'Submitting…' : 'Submit Release Request'}
        </button>
        <button type="button" onClick={onCancel} style={{ ...btnSmall, background: '#aaa' }}>Cancel</button>
      </div>
    </form>
  )
}

function ReleasesTab({ repoId }) {
  const [requests, setRequests] = useState([])
  const [loading, setLoading]   = useState(true)
  const [reviewer, setReviewer] = useState('')
  const [acting, setActing]     = useState(null)   // req id being approved/denied
  const [err, setErr]           = useState(null)

  const load = () => {
    listReleaseRequests(repoId)
      .then(setRequests)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [repoId])

  const handle = async (reqId, action) => {
    if (!reviewer.trim()) return setErr('Enter your name before approving or denying')
    setActing(reqId); setErr(null)
    try {
      if (action === 'approve') await approveReleaseRequest(repoId, reqId, { reviewed_by: reviewer })
      else await denyReleaseRequest(repoId, reqId, { reviewed_by: reviewer })
      load()
    } catch (e) { setErr(e.message) }
    finally { setActing(null) }
  }

  const pending  = requests.filter(r => r.status === 'pending')
  const history  = requests.filter(r => r.status !== 'pending')

  if (loading) return <p>Loading…</p>

  return (
    <div>
      {err && <p style={{ color: 'red', marginBottom: '12px' }}>{err}</p>}

      {/* Reviewer name — shared field for all approve/deny actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
        <span style={{ fontSize: '13px', color: '#555' }}>Your name (auditor):</span>
        <input value={reviewer} onChange={e => setReviewer(e.target.value)}
          placeholder="Enter your name to approve or deny"
          style={{ ...inputStyle, width: '260px' }} />
      </div>

      <h4 style={{ margin: '0 0 10px', fontSize: '14px' }}>
        Pending requests {pending.length > 0 && <span style={{ color: '#e67e22' }}>({pending.length})</span>}
      </h4>
      {pending.length === 0 && <p style={{ color: '#aaa', marginBottom: '20px' }}>No pending release requests.</p>}
      {pending.map(r => (
        <div key={r.id} style={{ ...rowStyle, alignItems: 'flex-start', gap: '12px', marginBottom: '8px' }}>
          <div style={{ flex: 1 }}>
            <code style={{ fontSize: '13px' }}>{r.part_number}</code>
            <span style={{ marginLeft: '10px', fontSize: '13px' }}>{r.title}</span>
            <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
              Requesting <strong>Rev {r.proposed_revision_code}</strong>
              {' · '}by {r.requested_by}
              {' · '}{new Date(r.created_at).toLocaleString()}
            </div>
            {r.change_note && (
              <div style={{ fontSize: '12px', color: '#555', marginTop: '3px', fontStyle: 'italic' }}>
                "{r.change_note}"
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
            <button disabled={!!acting} onClick={() => handle(r.id, 'approve')}
              style={{ ...btnSmall, background: '#1a5c2e', opacity: acting === r.id ? 0.6 : 1 }}>
              {acting === r.id ? '…' : '✓ Release'}
            </button>
            <button disabled={!!acting} onClick={() => handle(r.id, 'deny')}
              style={{ ...btnSmall, background: '#c0392b', opacity: acting === r.id ? 0.6 : 1 }}>
              ✕ Deny
            </button>
          </div>
        </div>
      ))}

      {history.length > 0 && (
        <>
          <h4 style={{ margin: '20px 0 10px', fontSize: '14px', color: '#888' }}>History</h4>
          {history.map(r => (
            <div key={r.id} style={{ ...rowStyle, opacity: 0.7, marginBottom: '6px' }}>
              <code style={{ fontSize: '13px' }}>{r.part_number}</code>
              <span style={{ marginLeft: '10px', flex: 1, fontSize: '13px' }}>{r.title}</span>
              <span style={{ fontSize: '12px', color: r.status === 'approved' ? 'green' : '#c0392b', marginRight: '10px' }}>
                {r.status === 'approved' ? `✓ Rev ${r.proposed_revision_code} released` : '✕ Denied'}
              </span>
              <span style={{ fontSize: '11px', color: '#aaa' }}>by {r.reviewed_by}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function ValidateTab({ validation }) {
  const [expanded, setExpanded] = useState({})   // doc_id → boolean

  const toggle = id => setExpanded(e => ({ ...e, [id]: !e[id] }))

  return (
    <div>
      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
        <Stat label="Total" value={validation.total} />
        <Stat label="Released" value={validation.released} color="green" />
        <Stat label="Unreleased" value={validation.unreleased} color="#e67e22" />
        <Stat label="No Drawing" value={validation.missing_drawing} color="red" />
        {validation.revision_mismatches > 0 && (
          <Stat label="Rev Mismatch" value={validation.revision_mismatches} color="#c0392b" />
        )}
      </div>
      {validation.documents.map(d => (
        <div key={d.document_id}>
          <div style={{ ...rowStyle, opacity: d.has_drawing ? 1 : 0.6 }}>
            <code style={{ fontSize: '13px', minWidth: '120px' }}>{d.part_number}</code>
            <span style={{ flex: 1, marginLeft: '12px' }}>{d.title}</span>
            {d.revision
              ? <span style={{ color: 'green', fontSize: '12px', marginRight: '8px' }}>Rev {d.revision}</span>
              : <span style={{ color: '#888', fontSize: '12px', marginRight: '8px' }}>Unreleased</span>}
            {d.revision_mismatch && (
              <span title={`File says REV-${d.title_revision}, vault assigned Rev ${d.revision}`}
                style={{ fontSize: '11px', color: '#c0392b', background: '#fdecea', padding: '2px 6px', borderRadius: '3px', marginRight: '8px', cursor: 'help' }}>
                ⚠ REV-{d.title_revision} ≠ Rev {d.revision}
              </span>
            )}
            {!d.has_drawing && <span style={{ color: 'red', fontSize: '12px', marginRight: '8px' }}>⚠ No drawing</span>}
            {d.missing_components?.length > 0 && (
              <button
                onClick={() => toggle(d.document_id)}
                style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'none', border: '1px solid #e67e22', borderRadius: '4px', color: '#e67e22', fontSize: '12px', padding: '2px 8px', cursor: 'pointer' }}
              >
                ⚠ {d.missing_components.length} missing part{d.missing_components.length > 1 ? 's' : ''}
                <span style={{ fontSize: '10px', transition: 'transform 0.15s', display: 'inline-block', transform: expanded[d.document_id] ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
              </button>
            )}
          </div>
          {expanded[d.document_id] && d.missing_components?.length > 0 && (
            <div style={{ marginLeft: '28px', marginBottom: '6px', padding: '8px 12px', background: '#fff8f0', border: '1px solid #fde8cc', borderRadius: '4px', borderTop: 'none' }}>
              <p style={{ margin: '0 0 6px', fontSize: '11px', color: '#b86a00', fontWeight: 600 }}>
                Referenced in drawing but not committed to this repository:
              </p>
              {d.missing_components.map(pn => (
                <div key={pn} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '3px 0' }}>
                  <code style={{ fontSize: '12px', background: '#fde8cc', padding: '1px 6px', borderRadius: '3px', color: '#b86a00' }}>{pn}</code>
                  <span style={{ fontSize: '11px', color: '#aaa' }}>not yet committed</span>
                </div>
              ))}
            </div>
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

// Live preview of the template derived from a sample part number — mirrors the
// backend: letters -> A, digits -> #, everything else kept literal.
function deriveTemplate(example) {
  return [...(example || '')].map(c =>
    /[A-Za-z]/.test(c) ? 'A' : /[0-9]/.test(c) ? '#' : c
  ).join('')
}

function SettingsTab({ repoId, mode }) {
  const [example, setExample] = useState('')
  const [savedExample, setSavedExample] = useState(null)
  const [scheme, setScheme] = useState('letters')
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    getRepoSettings(repoId)
      .then(s => {
        setExample(s.part_number_example || '')
        setSavedExample(s.part_number_example || null)
        setScheme(s.revision_scheme || 'letters')
      })
      .catch(() => {})
  }, [repoId])

  const template = deriveTemplate(example)

  const savePartNumber = async (clear = false) => {
    setErr(null); setMsg(null)
    try {
      const s = await updateRepoSettings(repoId, { part_number_example: clear ? null : example.trim() })
      setExample(s.part_number_example || '')
      setSavedExample(s.part_number_example || null)
      setMsg(clear ? 'Format cleared.' : `Saved — new documents must match ${s.part_number_template}`)
    } catch (e) { setErr(e.message) }
  }

  const saveScheme = async (newScheme) => {
    setErr(null); setMsg(null)
    try {
      const s = await updateRepoSettings(repoId, { revision_scheme: newScheme })
      setScheme(s.revision_scheme)
      setMsg(`Revision scheme set to ${s.revision_scheme === 'numbers' ? 'numbers (001, 002, 003)' : 'letters (A, B, C)'}.`)
    } catch (e) { setErr(e.message) }
  }

  const schemeBtn = (value, label) => (
    <button
      onClick={() => saveScheme(value)}
      style={{
        ...btnSmall,
        background: scheme === value ? '#1a1a2e' : '#e8e8f0',
        color: scheme === value ? '#fff' : '#444',
      }}
    >
      {label}
    </button>
  )

  return (
    <div style={{ maxWidth: '560px' }}>
      {/* Part-number format — set on the local vault (governs document creation) */}
      {mode === 'local' && (
        <>
          <h3 style={{ marginBottom: '4px' }}>Part-number format</h3>
          <p style={{ color: '#666', fontSize: '13px', marginTop: 0 }}>
            Enter a <strong>sample part number</strong>. New documents must match its shape, and the
            auto-BOM uses it to spot referenced parts. Leave empty to allow any format.
          </p>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
            <input
              value={example}
              onChange={e => { setExample(e.target.value); setMsg(null) }}
              placeholder="e.g. FW-PT-0001"
              style={{ ...inputStyle, flex: 1 }}
            />
            <button onClick={() => savePartNumber(false)} style={btnSmall} disabled={!example.trim()}>Save</button>
            {savedExample && (
              <button onClick={() => savePartNumber(true)} style={{ ...btnSmall, background: '#e8e8f0', color: '#444' }}>Clear</button>
            )}
          </div>
          {example.trim() && (
            <div style={{ fontSize: '13px', color: '#444', marginTop: '8px' }}>
              Template: <code style={{ background: '#f0f0f0', padding: '2px 8px', borderRadius: '4px' }}>{template}</code>
              <span style={{ color: '#888', marginLeft: '8px', fontSize: '12px' }}>(A = letter, # = digit)</span>
            </div>
          )}
        </>
      )}

      {/* Revision scheme — set on the remote vault (governs releases) */}
      {mode === 'remote' && (
        <>
          <h3 style={{ marginBottom: '4px' }}>Revision scheme</h3>
          <p style={{ color: '#666', fontSize: '13px', marginTop: 0 }}>
            The code used when publishing revisions on this vault. Releases must move forward in
            whichever scheme you pick (skips allowed; no duplicates or going backward).
          </p>
          <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
            {schemeBtn('letters', 'Letters — A, B, C')}
            {schemeBtn('numbers', 'Numbers — 001, 002, 003')}
          </div>
        </>
      )}

      {msg && <div style={{ fontSize: '13px', color: 'green', marginTop: '12px' }}>{msg}</div>}
      {err && <div style={{ fontSize: '13px', color: '#c0392b', marginTop: '12px' }}>{err}</div>}
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
            {f.current_pdf_url
              ? <a href={f.current_pdf_url} target="_blank" rel="noreferrer" style={{ fontSize: '12px', color: '#1a1a2e' }}>Current PDF ↗</a>
              : <span style={{ fontSize: '12px', color: '#aaa' }}>PDF unavailable</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

const btnSmall = { padding: '5px 12px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }
const rowStyle = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', padding: '10px 12px', border: '1px solid #eee', borderRadius: '4px', marginBottom: '6px' }
const inputStyle = { padding: '6px 10px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '13px' }
