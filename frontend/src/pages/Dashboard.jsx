import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listRepos, createRepo } from '../api'

export default function Dashboard() {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', watch_path: '' })
  const navigate = useNavigate()

  useEffect(() => {
    listRepos()
      .then(setRepos)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = async e => {
    e.preventDefault()
    try {
      const repo = await createRepo(form)
      navigate(`/repos/${repo.id}`)
    } catch (e) {
      alert(e.message)
    }
  }

  if (loading) return <p>Loading repositories…</p>
  if (error) return <p style={{ color: 'red' }}>Error: {error}</p>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ margin: 0 }}>Repositories</h2>
        <button onClick={() => setShowNew(!showNew)} style={btnStyle}>+ New Repository</button>
      </div>

      {showNew && (
        <form onSubmit={handleCreate} style={{ background: '#f5f5f5', padding: '16px', borderRadius: '6px', marginBottom: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input required placeholder="Repository name" value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              style={inputStyle} />
            <input placeholder="Description (optional)" value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              style={{ ...inputStyle, flex: 2 }} />
          </div>
          <div>
            <input
              placeholder="Directory to watch (relative to home, e.g. Desktop/drawings)"
              value={form.watch_path}
              onChange={e => setForm({ ...form, watch_path: e.target.value })}
              style={{ ...inputStyle, width: '100%', boxSizing: 'border-box' }}
            />
            <div style={{ fontSize: '11px', color: '#999', marginTop: '3px' }}>
              Like <code>git init</code> — this folder is permanently linked to the repo. Leave blank for remote-only repos.
            </div>
          </div>
          <div>
            <button type="submit" style={btnStyle}>Create</button>
          </div>
        </form>
      )}

      {repos.length === 0 && <p style={{ color: '#888' }}>No repositories yet. Create one to get started.</p>}

      {repos.map(r => (
        <Link key={r.id} to={`/repos/${r.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
          <div style={cardStyle}>
            {/* top row: repo name + description */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
              <strong style={{ fontSize: '16px' }}>{r.name}</strong>
              {r.description && <span style={{ color: '#666', fontSize: '14px' }}>{r.description}</span>}
            </div>

            {/* stats row: document count and latest commit */}
            <div style={{ display: 'flex', gap: '24px', marginTop: '8px', fontSize: '12px', color: '#888' }}>
              {/* document_count comes from the enriched list endpoint */}
              <span>{r.document_count} document{r.document_count !== 1 ? 's' : ''}</span>

              {r.latest_commit ? (
                // show the most recent commit hash, author, and message
                <span>
                  Last commit{' '}
                  <code style={{ background: '#f0f0f0', padding: '1px 4px', borderRadius: '3px' }}>
                    {r.latest_commit.hash}
                  </code>
                  {' '}by {r.latest_commit.author} — {r.latest_commit.message}
                </span>
              ) : (
                <span style={{ color: '#ccc' }}>No commits yet</span>
              )}
            </div>

            <div style={{ marginTop: '6px', fontSize: '11px', color: '#bbb' }}>
              Created {new Date(r.created_at).toLocaleDateString()}
            </div>
          </div>
        </Link>
      ))}
    </div>
  )
}

const btnStyle = { padding: '8px 16px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }
const inputStyle = { padding: '8px', border: '1px solid #ccc', borderRadius: '4px', flex: 1 }
const cardStyle = { border: '1px solid #ddd', borderRadius: '6px', padding: '16px', marginBottom: '10px', cursor: 'pointer', transition: 'background .15s' }
