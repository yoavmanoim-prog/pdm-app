import { useEffect, useState } from 'react'
import { browseWatch } from '../api'

const isLocalApp = window.location.hostname === 'localhost'

export default function FolderPicker({ value, onChange }) {
  const [open, setOpen]     = useState(false)
  const [browsing, setBrowsing] = useState('')   // current path in browser
  const [dirs, setDirs]     = useState([])
  const [parent, setParent] = useState(null)
  const [error, setError]   = useState(null)

  const load = (path) => {
    setError(null)
    browseWatch(path)
      .then(d => { setDirs(d.dirs); setBrowsing(d.current); setParent(d.parent) })
      .catch(() => setError('Cannot reach local vault — make sure docker-compose is running'))
  }

  useEffect(() => { if (open) load('') }, [open])

  const select = (path) => {
    onChange(path)
    setOpen(false)
  }

  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'flex', gap: '6px' }}>
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder="DevOps/projects/drawings"
          style={{ flex: 1, padding: '7px', border: '1px solid var(--border)', borderRadius: '4px', fontSize: '13px' }}
        />
        {isLocalApp && (
          <button type="button" onClick={() => setOpen(!open)}
            style={{ padding: '7px 12px', border: '1px solid var(--border)', borderRadius: '4px', cursor: 'pointer', background: 'var(--surface-2)', fontSize: '13px' }}>
            Browse
          </button>
        )}
      </div>

      {open && (
        <div style={{
          position: 'absolute', top: '36px', left: 0, right: 0, zIndex: 200,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px',
          boxShadow: '0 4px 16px rgba(0,0,0,0.12)', maxHeight: '260px', overflowY: 'auto',
        }}>
          {/* header */}
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-soft)', fontSize: '12px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
            <span>/{browsing || 'home'}</span>
            <button type="button" onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '14px', color: 'var(--text-faint)' }}>✕</button>
          </div>

          {error && <div style={{ padding: '10px 12px', color: 'var(--danger)', fontSize: '13px' }}>{error}</div>}

          {/* up button */}
          {parent !== null && parent !== undefined && (
            <div onClick={() => load(parent)} style={rowStyle}>
              <span style={{ color: 'var(--text-muted)' }}>← ..</span>
            </div>
          )}

          {/* select current dir */}
          {browsing && (
            <div onClick={() => select(browsing)} style={{ ...rowStyle, color: 'var(--accent)', fontWeight: 600 }}>
              ✓ Select this folder
            </div>
          )}

          {dirs.length === 0 && !error && (
            <div style={{ padding: '10px 12px', color: 'var(--text-faint)', fontSize: '13px' }}>No subfolders here</div>
          )}

          {dirs.map(d => (
            <div key={d.path} style={rowStyle} onClick={() => load(d.path)}>
              📁 {d.name}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const rowStyle = {
  padding: '9px 14px', cursor: 'pointer', fontSize: '13px',
  borderBottom: '1px solid var(--surface-2)',
  transition: 'background 0.1s',
  onMouseEnter: e => e.target.style.background = 'var(--surface-2)',
}
