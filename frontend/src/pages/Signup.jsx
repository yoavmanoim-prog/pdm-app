import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await signup(email, password, fullName || null)
      navigate('/', { replace: true })   // signup logs you straight in
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginTop: 0 }}>Create account</h2>
      <form onSubmit={handleSubmit} style={form}>
        <input placeholder="Full name (optional)" value={fullName}
          onChange={e => setFullName(e.target.value)} style={input} />
        <input type="email" required placeholder="Email" value={email}
          onChange={e => setEmail(e.target.value)} style={input} />
        <input type="password" required minLength={8} placeholder="Password (min 8 chars)" value={password}
          onChange={e => setPassword(e.target.value)} style={input} />
        {error && <p style={{ color: 'var(--danger)', margin: 0 }}>{error}</p>}
        <button type="submit" disabled={busy} style={btn}>{busy ? 'Creating…' : 'Create account'}</button>
      </form>
      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </div>
  )
}

const card = { maxWidth: 380, margin: '72px auto', padding: 28, border: '1px solid var(--border)', borderRadius: 12, background: 'var(--surface)', boxShadow: 'var(--shadow)' }
const form = { display: 'flex', flexDirection: 'column', gap: 12 }
const input = { padding: '10px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 14 }
const btn = { padding: '10px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 4, fontSize: 14, cursor: 'pointer' }
