import { useState } from 'react'
import { useMode } from '../context/ModeContext'

export default function ModeToggle() {
  const { mode, switchMode, remoteUrl, setRemoteUrl } = useMode()
  const [editing, setEditing] = useState(false)
  const [urlInput, setUrlInput] = useState(remoteUrl)
  const isLocalhost = window.location.hostname === 'localhost'

  const pillStyle = (active) => ({
    padding: '4px 14px',
    borderRadius: '20px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: 600,
    background: active ? '#1a1a2e' : '#e8e8f0',
    color: active ? '#fff' : '#555',
    transition: 'all 0.15s',
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ display: 'flex', background: '#e8e8f0', borderRadius: '20px', padding: '2px', gap: '2px' }}>
        <button style={pillStyle(mode === 'local')} onClick={() => switchMode('local')}>
          Local Vault
        </button>
        <button style={pillStyle(mode === 'remote')} onClick={() => switchMode('remote')}>
          Remote Vault
        </button>
      </div>

      {/* show config icon on localhost so user can set the remote URL */}
      {isLocalhost && mode === 'remote' && (
        <button
          onClick={() => setEditing(!editing)}
          title="Set remote vault URL"
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px', padding: '2px' }}
        >
          ⚙
        </button>
      )}

      {editing && (
        <div style={{
          position: 'absolute', top: '52px', right: '20px', zIndex: 100,
          background: '#fff', border: '1px solid #ddd', borderRadius: '8px',
          padding: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', minWidth: '320px',
        }}>
          <div style={{ fontSize: '12px', color: '#666', marginBottom: '6px' }}>Remote vault URL</div>
          <div style={{ display: 'flex', gap: '6px' }}>
            <input
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              placeholder="https://d3df2y18th5fg7.cloudfront.net"
              style={{ flex: 1, padding: '6px 10px', border: '1px solid #ccc', borderRadius: '6px', fontSize: '13px' }}
            />
            <button
              onClick={() => { setRemoteUrl(urlInput); setEditing(false); window.location.reload() }}
              style={{ padding: '6px 12px', background: '#1a1a2e', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
