import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // where to send the user after login: back to the page that bounced them here,
  // or the dashboard if they came straight to /login.
  const from = location.state?.from || '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={card}>
      <h2 style={{ marginTop: 0 }}>Sign in</h2>
      <form onSubmit={handleSubmit} style={form}>
        <input type="email" required placeholder="Email" value={email}
          onChange={e => setEmail(e.target.value)} style={input} />
        <input type="password" required placeholder="Password" value={password}
          onChange={e => setPassword(e.target.value)} style={input} />
        {error && <p style={{ color: 'var(--danger)', margin: 0 }}>{error}</p>}
        <button type="submit" disabled={busy} style={btn}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
        No account? <Link to="/signup">Create one</Link>
      </p>
    </div>
  )
}

const card = { maxWidth: 380, margin: '72px auto', padding: 28, border: '1px solid var(--border)', borderRadius: 12, background: 'var(--surface)', boxShadow: 'var(--shadow)' }
const form = { display: 'flex', flexDirection: 'column', gap: 12 }
const input = { padding: '10px', border: '1px solid var(--border)', borderRadius: 4, fontSize: 14 }
const btn = { padding: '10px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 4, fontSize: 14, cursor: 'pointer' }
