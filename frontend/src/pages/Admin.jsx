import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listUsers, createUser, updateUser, deleteUser, listRoles } from '../api'
import { useAuth } from '../context/AuthContext'

// Admin console: list every account and change roles / active state. This is the
// UI side of "the admin grants permissions" — flip a user between member/admin
// or deactivate them. Route guarding (admin-only) happens in App.jsx; the
// backend re-checks the role too, so this page can't be reached or abused by a
// member even if they hand-craft the URL.
export default function Admin() {
  const { user: me, can } = useAuth()
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ email: '', password: '', full_name: '', role: 'member' })

  function refresh() {
    setLoading(true)
    listUsers().then(setUsers).catch(e => setError(e.message)).finally(() => setLoading(false))
  }
  // roles populate the assignment dropdowns; loaded once
  useEffect(() => { refresh(); listRoles().then(setRoles).catch(() => {}) }, [])

  async function handleCreate(e) {
    e.preventDefault()
    try {
      await createUser(form)
      setForm({ email: '', password: '', full_name: '', role: 'member' })
      refresh()
    } catch (err) { alert(err.message) }
  }

  async function changeRole(u, role) {
    try { await updateUser(u.id, { role }); refresh() } catch (err) { alert(err.message) }
  }
  async function toggleActive(u) {
    try { await updateUser(u.id, { is_active: !u.is_active }); refresh() } catch (err) { alert(err.message) }
  }
  async function remove(u) {
    if (!confirm(`Delete ${u.email}?`)) return
    try { await deleteUser(u.id); refresh() } catch (err) { alert(err.message) }
  }

  if (loading) return <p>Loading users…</p>
  if (error) return <p style={{ color: 'var(--danger)' }}>Error: {error}</p>

  const roleOptions = (roles.length ? roles.map(r => r.name) : ['member', 'admin'])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2>User management</h2>
        {can('manage_roles') && <Link to="/roles" style={{ fontSize: 14 }}>Manage roles →</Link>}
      </div>

      <form onSubmit={handleCreate} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', background: 'var(--surface-2)', padding: 12, borderRadius: 6, marginBottom: 20 }}>
        <input required type="email" placeholder="Email" value={form.email}
          onChange={e => setForm({ ...form, email: e.target.value })} style={input} />
        <input required type="password" minLength={8} placeholder="Password" value={form.password}
          onChange={e => setForm({ ...form, password: e.target.value })} style={input} />
        <input placeholder="Full name" value={form.full_name}
          onChange={e => setForm({ ...form, full_name: e.target.value })} style={input} />
        <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })} style={input}>
          {roleOptions.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <button type="submit" style={btn}>+ Add user</button>
      </form>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '2px solid var(--accent)' }}>
            <th style={th}>Email</th><th style={th}>Name</th><th style={th}>Role</th>
            <th style={th}>Status</th><th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id} style={{ borderBottom: '1px solid var(--border-soft)' }}>
              <td style={td}>{u.email}{u.id === me?.id && <span style={{ color: 'var(--text-muted)' }}> (you)</span>}</td>
              <td style={td}>{u.full_name || '—'}</td>
              <td style={td}>
                <select value={u.role} onChange={e => changeRole(u, e.target.value)} style={input}>
                  {roleOptions.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </td>
              <td style={td}>{u.is_active
                ? <span style={{ color: 'var(--success)' }}>active</span>
                : <span style={{ color: 'var(--danger)' }}>disabled</span>}</td>
              <td style={td}>
                <button onClick={() => toggleActive(u)} style={smallBtn}>
                  {u.is_active ? 'Deactivate' : 'Activate'}
                </button>
                <button onClick={() => remove(u)} style={{ ...smallBtn, color: 'var(--danger)' }}>Delete</button>
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
const smallBtn = { padding: '4px 8px', marginRight: 6, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', fontSize: 12 }
const th = { padding: '8px 6px' }
const td = { padding: '8px 6px' }
