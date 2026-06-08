import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getDocumentCommits } from '../api'

export default function DocumentViewer() {
  const { repoId, docId } = useParams()
  const [data, setData] = useState(null)       // { document_id, part_number, title, doc_type, versions[] }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // the version the user clicked — defaults to the latest (index 0)
  const [selected, setSelected] = useState(0)

  useEffect(() => {
    getDocumentCommits(repoId, docId)
      .then(d => { setData(d); setSelected(0) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [repoId, docId])

  if (loading) return <p>Loading document…</p>
  if (error)   return <p style={{ color: 'red' }}>{error}</p>
  if (!data)   return null

  const version = data.versions[selected]  // the currently selected version entry

  return (
    <div>
      {/* breadcrumb navigation */}
      <Link to={`/repos/${repoId}`} style={{ color: '#888', fontSize: '13px' }}>
        ← Back to repository
      </Link>

      {/* document header */}
      <div style={{ margin: '8px 0 20px' }}>
        <h2 style={{ margin: '4px 0' }}>{data.part_number} — {data.title}</h2>
        <span style={{ fontSize: '12px', color: '#888', background: '#f0f0f0', padding: '2px 8px', borderRadius: '3px' }}>
          {data.doc_type}
        </span>
      </div>

      <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>

        {/* LEFT PANEL — version list */}
        <div style={{ width: '260px', flexShrink: 0 }}>
          <h3 style={{ fontSize: '14px', margin: '0 0 10px', color: '#555' }}>
            {data.versions.length} version{data.versions.length !== 1 ? 's' : ''}
          </h3>

          {data.versions.length === 0 && (
            <p style={{ color: '#aaa', fontSize: '13px' }}>No commits for this document yet.</p>
          )}

          {data.versions.map((v, i) => (
            <button
              key={v.commit_hash}
              onClick={() => setSelected(i)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '10px 12px', marginBottom: '6px',
                border: '1px solid ' + (i === selected ? '#1a1a2e' : '#eee'),
                borderRadius: '4px', background: i === selected ? '#1a1a2e' : '#fff',
                color: i === selected ? '#fff' : '#333', cursor: 'pointer',
              }}
            >
              {/* commit hash badge */}
              <code style={{
                fontSize: '11px', padding: '1px 5px', borderRadius: '3px',
                background: i === selected ? 'rgba(255,255,255,.2)' : '#f0f0f0',
                color: i === selected ? '#fff' : '#333',
              }}>
                {v.commit_hash}
              </code>
              {/* change type badge: "added" or "modified" */}
              <span style={{
                marginLeft: '6px', fontSize: '10px', padding: '1px 5px', borderRadius: '3px',
                background: v.change_type === 'added' ? '#d4edda' : '#fff3cd',
                color: v.change_type === 'added' ? '#155724' : '#856404',
              }}>
                {v.change_type}
              </span>
              <div style={{ fontSize: '12px', marginTop: '4px', fontWeight: i === selected ? 600 : 400 }}>
                {v.message}
              </div>
              <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.7 }}>
                {v.author} · {new Date(v.timestamp).toLocaleString()}
              </div>
            </button>
          ))}
        </div>

        {/* RIGHT PANEL — PDF viewer(s) */}
        <div style={{ flex: 1 }}>
          {!version && <p style={{ color: '#aaa' }}>Select a version to view the PDF.</p>}

          {version && (
            <>
              {/* current version PDF */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: '#333' }}>
                  Current — <code style={{ fontWeight: 400 }}>{version.commit_hash}</code>
                  {' '}· {version.author}
                </div>
                {version.current_pdf_url ? (
                  // browser-native PDF rendering — no extra library needed
                  <iframe
                    src={version.current_pdf_url}
                    title="Current PDF"
                    style={{ width: '100%', height: '520px', border: '1px solid #ddd', borderRadius: '4px' }}
                  />
                ) : (
                  <p style={{ color: '#aaa', fontSize: '13px' }}>PDF not available for this version.</p>
                )}
              </div>

              {/* previous version PDF — only shown when this commit has a parent version */}
              {version.previous_pdf_url && (
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: '#888' }}>
                    Previous version (before this commit)
                  </div>
                  <iframe
                    src={version.previous_pdf_url}
                    title="Previous PDF"
                    style={{ width: '100%', height: '520px', border: '1px solid #eee', borderRadius: '4px' }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
