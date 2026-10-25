import { useState } from 'react'
import { KeyRound, LogIn, UserPlus } from 'lucide-react'
import { API_BASE, setAccessToken } from '../services/api'

interface AuthenticatedAccount {
  user_id: string
  username: string
}

interface AuthResponse {
  access_token: string
  user: AuthenticatedAccount
}

export default function AuthPanel({ onAuthenticated }: {
  onAuthenticated: (token: string, user: AuthenticatedAccount) => void
}) {
  const [mode, setMode] = useState<'login' | 'register'>('register')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const response = await fetch(`${API_BASE}/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Authentication failed')
      const result = data as AuthResponse
      setAccessToken(result.access_token)
      onAuthenticated(result.access_token, result.user)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Could not reach FedMeta')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-8 shadow-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600">
            {mode === 'register' ? <UserPlus size={25} /> : <KeyRound size={25} />}
          </div>
          <h1 className="text-2xl font-bold">FedMeta</h1>
          <p className="mt-2 text-sm text-gray-400">
            {mode === 'register' ? 'Create a local account to get started' : 'Sign in to your local account'}
          </p>
        </div>

        <label className="mb-4 block text-sm text-gray-300">
          Username
          <input
            autoComplete="username"
            required
            minLength={3}
            maxLength={32}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-gray-100 outline-none focus:border-blue-500"
            placeholder="3–32 letters, numbers, ., _ or -"
          />
        </label>

        <label className="mb-5 block text-sm text-gray-300">
          Password
          <input
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            required
            minLength={10}
            maxLength={128}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-gray-100 outline-none focus:border-blue-500"
            placeholder="At least 10 characters"
          />
        </label>

        {error && <p role="alert" className="mb-4 rounded-lg border border-red-800 bg-red-950/50 p-3 text-sm text-red-300">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 font-medium text-white transition hover:bg-blue-500 disabled:cursor-wait disabled:opacity-60"
        >
          {mode === 'register' ? <UserPlus size={17} /> : <LogIn size={17} />}
          {busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Sign in'}
        </button>

        <p className="mt-5 text-center text-sm text-gray-400">
          {mode === 'register' ? 'Already registered?' : 'New to FedMeta?'}{' '}
          <button
            type="button"
            onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError('') }}
            className="font-medium text-blue-400 hover:text-blue-300"
          >
            {mode === 'register' ? 'Sign in' : 'Create account'}
          </button>
        </p>
        <p className="mt-4 text-center text-xs text-gray-600">Local development account · no email required</p>
      </form>
    </div>
  )
}
