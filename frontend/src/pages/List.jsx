import { useEffect, useState } from 'react'

// List page — shows all uploaded schematics and lets the user search
export default function List() {
  const [schematics, setSchematics] = useState([]) // stores the list fetched from the API
  const [search, setSearch] = useState('')          // stores what the user types in the search box
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Fetch schematics from the backend when the page loads
  useEffect(() => {
    fetch('/api/schematics')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch schematics')
        return res.json()
      })
      .then(data => {
        setSchematics(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  // Filter the list based on what the user typed
  const filtered = schematics.filter(s =>
    s.part_number.toLowerCase().includes(search.toLowerCase()) ||
    (s.vehicle_make || '').toLowerCase().includes(search.toLowerCase()) ||
    (s.model || '').toLowerCase().includes(search.toLowerCase())
  )

  // Ask the backend for a temporary download link then open it in a new tab
  const handleDownload = (id) => {
    fetch(`/api/schematics/${id}/download`)
      .then(res => res.json())
      .then(data => window.open(data.url, '_blank'))
      .catch(() => alert('Download failed'))
  }

  if (loading) return <p>Loading...</p>
  if (error) return <p style={{ color: 'var(--danger)' }}>Error: {error}</p>

  return (
    <div>
      <h2>Schematics</h2>

      {/* Search box — filters the list as the user types */}
      <input
        type="text"
        placeholder="Search by part number, make or model..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{ width: '100%', padding: '8px', marginBottom: '20px', fontSize: '14px' }}
      />

      {filtered.length === 0 && <p>No schematics found.</p>}

      {/* One card per schematic */}
      {filtered.map(s => (
        <div key={s.id} style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '16px', marginBottom: '12px' }}>
          <strong>{s.part_number}</strong>
          {s.vehicle_make && <span style={{ marginLeft: '10px', color: 'var(--text-muted)' }}>{s.vehicle_make} {s.model}</span>}
          {s.description && <p style={{ margin: '6px 0', color: 'var(--text)' }}>{s.description}</p>}
          <small style={{ color: 'var(--text-faint)' }}>Version {s.version} · Uploaded {new Date(s.created_at).toLocaleDateString()}</small>
          <br />
          <button
            onClick={() => handleDownload(s.id)}
            style={{ marginTop: '10px', padding: '6px 14px', cursor: 'pointer' }}
          >
            Download PDF
          </button>
        </div>
      ))}
    </div>
  )
}
