import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Network } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate  = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [pending, setPending]   = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setPending(true)
    try {
      await login(username, password)
      navigate('/', { replace: true })
    } catch {
      setError('Invalid username or password')
    } finally {
      setPending(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)',
    }}>
      <div style={{
        width: '320px', padding: '2rem',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: '10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <Network size={20} />
          <span style={{ fontWeight: 600, fontSize: '1.1rem' }}>IPForge</span>
        </div>

        <form onSubmit={submit}>
          <div className="form-field" style={{ marginBottom: '0.75rem' }}>
            <label>Username</label>
            <input
              autoFocus
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
            />
          </div>
          <div className="form-field" style={{ marginBottom: '1rem' }}>
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && (
            <div className="feedback-error" style={{ marginBottom: '0.75rem', fontSize: '0.8rem' }}>
              {error}
            </div>
          )}
          <button
            type="submit"
            className="btn-primary"
            style={{ width: '100%' }}
            disabled={pending || !username || !password}
          >
            {pending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
