import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getMergeRequest, executeMerge } from '../api'

export default function BranchView() {
  const { repoId, branchId } = useParams()
  const navigate = useNavigate()
  const [preview, setPreview] = useState(null)
  const [author, setAuthor] = useState('')
  const [loading, setLoading] = useState(true)
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getMergeRequest(repoId, branchId)
      .then(setPreview)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [repoId, branchId])

  const handleMerge = async () => {
    if (!author.trim()) return alert('Enter your name to execute the merge')
    if (!window.confirm(`Merge branch into main? This cannot be undone.`)) return
    setMerging(true)
    try {
      await executeMerge(repoId, branchId, author)
      alert('Merged successfully!')
      navigate(`/repos/${repoId}`)
    } catch (e) {
      alert(e.message)
    } finally {
      setMerging(false)
    }
  }

  if (loading) return <p>Loading merge request…</p>
  if (error) return <p style={{ color: 'red' }}>{error}</p>
  if (!preview) return null

  return (
    <div>
      <Link to={`/repos/${repoId}`} style={{ color: '#888', fontSize: '13px' }}>← Back to repository</Link>
      <h2 style={{ margin: '8px 0' }}>Merge Request — {preview.branch}</h2>

      {/* Conflict report */}
      {preview.conflicts.length > 0 && (
        <div style={{ background: '#ffeaea', border: '1px solid #e74c3c', borderRadius: '6px', padding: '14px', marginBottom: '16px' }}>
          <strong style={{ color: '#e74c3c' }}>⚠ Conflicts detected — merge is blocked</strong>
          <p style={{ margin: '6px 0 0', fontSize: '13px', color: '#666' }}>
            The following documents were changed on both this branch and main since the branch was created.
            Resolve the conflict by ensuring only one side has changes before merging.
          </p>
          <ul style={{ margin: '8px 0 0', paddingLeft: '20px', fontSize: '13px' }}>
            {preview.conflicts.map(id => <li key={id}><code>{id}</code></li>)}
          </ul>
        </div>
      )}

      {/* Changed files */}
      <h3>Changes in this branch ({preview.changed_files.length} document{preview.changed_files.length !== 1 ? 's' : ''})</h3>
      {preview.changed_files.length === 0 && <p style={{ color: '#888' }}>No changes on this branch yet.</p>}
      {preview.changed_files.map(f => (
        <div key={f.document_id} style={{ display: 'flex', alignItems: 'center', padding: '10px 12px', border: '1px solid #eee', borderRadius: '4px', marginBottom: '6px' }}>
          <span style={{ fontSize: '12px', padding: '2px 8px', borderRadius: '3px', marginRight: '12px',
            background: f.change_type === 'added' ? '#d4edda' : '#fff3cd',
            color: f.change_type === 'added' ? '#155724' : '#856404' }}>
            {f.change_type}
          </span>
          <code style={{ flex: 1, fontSize: '13px' }}>{f.document_id}</code>
          <span style={{ fontSize: '11px', color: '#aaa' }}>{f.content_hash?.slice(0, 12)}…</span>
        </div>
      ))}

      {/* Merge action */}
      {preview.can_merge && (
        <div style={{ marginTop: '24px', padding: '16px', background: '#f0fff4', border: '1px solid #2ecc71', borderRadius: '6px' }}>
          <strong style={{ color: '#27ae60' }}>✓ No conflicts — ready to merge</strong>
          <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
            <input
              placeholder="Your name (required)"
              value={author}
              onChange={e => setAuthor(e.target.value)}
              style={{ padding: '8px', border: '1px solid #ccc', borderRadius: '4px', flex: 1 }}
            />
            <button onClick={handleMerge} disabled={merging}
              style={{ padding: '8px 20px', background: '#27ae60', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
              {merging ? 'Merging…' : 'Execute Merge'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
