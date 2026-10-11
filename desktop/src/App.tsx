import { useState } from 'react'
import ProfileTab from './components/ProfileTab'
import ToolsTab from './components/ToolsTab'
import LearningTab from './components/LearningTab'
import ChatPanel from './components/ChatPanel'
import { User, Wrench, Brain, MessageSquare } from 'lucide-react'

type Tab = 'profile' | 'tools' | 'learning' | 'chat'

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('profile')
  const [userId, setUserId] = useState('user_001')

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

        <div className="p-4 border-b border-gray-700">
          <label className="text-xs text-gray-400 block mb-1">User ID</label>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-gray-100 focus:outline-none focus:border-blue-500"
          />
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
