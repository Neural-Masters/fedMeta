import { useEffect, useState } from 'react'
import ProfileTab from './components/ProfileTab'
import ToolsTab from './components/ToolsTab'
import LearningTab from './components/LearningTab'
import ChatPanel from './components/ChatPanel'
import AuthPanel from './components/AuthPanel'
import { User, Wrench, Brain, MessageSquare, LogOut } from 'lucide-react'
import { apiFetch, clearAccessToken, getAccessToken } from './services/api'

type Tab = 'profile' | 'tools' | 'learning' | 'chat'
interface Account { user_id: string; username: string }

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const [account, setAccount] = useState<Account | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setCheckingSession(false)
      return
    }
    apiFetch('/auth/me')
      .then(async (response) => {
        if (!response.ok) throw new Error('Session expired')
        setAccount(await response.json())
      })
      .catch(() => clearAccessToken())
      .finally(() => setCheckingSession(false))
  }, [])

  const signOut = async () => {
    try { await apiFetch('/auth/logout', { method: 'POST' }) } catch { /* clear local session regardless */ }
    clearAccessToken()
    setAccount(null)
    setActiveTab('profile')
  }

  if (checkingSession) {
    return <div className="flex h-screen items-center justify-center bg-gray-900 text-gray-400">Checking local session…</div>
  }
  if (!account) {
    return <AuthPanel onAuthenticated={(_token, user) => setAccount(user)} />
  }

  const userId = account.user_id

  const tabs = [
    { id: 'profile' as Tab, label: 'Profile', icon: User },
    { id: 'tools' as Tab, label: 'API Tools', icon: Wrench },
    { id: 'learning' as Tab, label: 'Learning', icon: Brain },
    { id: 'chat' as Tab, label: 'Chat', icon: MessageSquare },
  ]

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Sidebar */}
      <nav className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-6 border-b border-gray-700">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            FedMeta
          </h1>
          <p className="text-xs text-gray-400 mt-1">Adaptive Profile Framework</p>
        </div>

        <div className="flex items-center gap-3 border-b border-gray-700 p-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gray-700 text-sm font-semibold text-blue-300">
            {account.username.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-gray-200">{account.username}</p>
            <p className="text-xs text-gray-500">Signed in</p>
          </div>
          <button onClick={signOut} title="Sign out" className="rounded-lg p-2 text-gray-500 transition hover:bg-gray-700 hover:text-gray-200">
            <LogOut size={16} />
          </button>
        </div>

        <ul className="flex-1 p-4 space-y-1">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <li key={tab.id}>
                <button
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                  }`}
                >
                  <Icon size={18} />
                  {tab.label}
                </button>
              </li>
            )
          })}
        </ul>

        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <div className="w-2 h-2 rounded-full bg-green-500" />
            Server: localhost:8000
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        {activeTab === 'profile' && <ProfileTab userId={userId} />}
        {activeTab === 'tools' && <ToolsTab userId={userId} />}
        {activeTab === 'learning' && <LearningTab userId={userId} />}
        {activeTab === 'chat' && <ChatPanel userId={userId} />}
      </main>
    </div>
  )
}
