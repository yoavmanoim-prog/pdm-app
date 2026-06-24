import { useEffect, useState } from 'react'
import { listRoles, createRole, updateRole, deleteRole } from '../api'

// Role management: an admin builds roles (e.g. engineer / checker / manager) by
// bundling privileges, then assigns them on the Users page. Route-guarded to
// manage_roles in App.jsx; the backend re-checks every call.

// keep in sync with backend app/authz.PRIVILEGES (with friendly labels)
const ALL_PRIVILEGES = [
  ['manage_users', 'Manage users (create / assign roles)'],
  ['manage_roles', 'Manage roles'],
  ['approve_drawing', 'Approve drawings (sign off before push)'],
  ['approve_release', 'Approve / publish releases'],
]

export default function Roles() {
  const [roles, setRoles] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ name: '', privileges: [] })

  function refresh() {
    setLoading(true)
    listRoles().then(setRoles).catch(e => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(refresh, [])

  function togglePriv(set, priv) {
    return set.includes(priv) ? set.filter(p => p !== priv) : [...set, priv]
  }

  async function handleCreate(e) {
    e.preventDefault()
    try {
      await createRole(form)
      setForm({ name: '', privileges: [] })
      refresh()
    } catch (err) { alert(err.message) }
  }

  async function savePrivs(role, privileges) {
    try { await updateRole(role.id, { privileges }); refresh() } catch (err) { alert(err.message) }
  }
  async function remove(role) {
    if (!confirm(`Delete role "${role.name}"?`)) return
    try { await deleteRole(role.id); refresh() } catch (err) { alert(err.message) }
  }

  if (loading) return <p>Loading roles…</p>
  if (error) return <p style={{ color: 'var(--danger)' }}>Error: {error}</p>

  return (
    <div>
      <h2>Role management</h2>

      {/* create a new role */}
      <form onSubmit={handleCreate} style={{ background: 'var(--surface-2)', padding: 14, borderRadius: 6, marginBottom: 24 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
          <input required placeholder="New role name (e.g. checker)" value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })} style={input} />
          <button type="submit" style={btn}>+ Create role</button>
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {ALL_PRIVILEGES.map(([priv, label]) => (
            <label key={priv} style={{ fontSize: 13 }}>
              <input type="checkbox" checked={form.privileges.includes(priv)}
                onChange={() => setForm({ ...form, privileges: togglePriv(form.privileges, priv) })} /> {label}
            </label>
          ))}
        </div>
      </form>

      {/* existing roles — edit privileges inline (built-ins are read-only) */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '2px solid var(--accent)' }}>
            <th style={th}>Role</th><th style={th}>Privileges</th><th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {roles.map(role => (
            <tr key={role.id} style={{ borderBottom: '1px solid var(--border-soft)' }}>
              <td style={td}>
                {role.name}{role.is_builtin && <span style={{ color: 'var(--text-muted)' }}> (built-in)</span>}
              </td>
              <td style={td}>
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                  {ALL_PRIVILEGES.map(([priv, label]) => (
                    <label key={priv} style={{ fontSize: 12, color: role.is_builtin ? 'var(--text-faint)' : 'var(--text)' }}>
                      <input type="checkbox" disabled={role.is_builtin}
                        checked={role.privileges.includes(priv)}
                        onChange={() => savePrivs(role, togglePriv(role.privileges, priv))} /> {priv}
                    </label>
                  ))}
                </div>
              </td>
              <td style={td}>
                {!role.is_builtin && (
                  <button onClick={() => remove(role)} style={{ ...smallBtn, color: 'var(--danger)' }}>Delete</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const input = { padding: '8px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 13 }
const btn = { padding: '8px 14px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }
const smallBtn = { padding: '4px 8px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', fontSize: 12 }
const th = { padding: '8px 6px' }
const td = { padding: '8px 6px', verticalAlign: 'top' }
