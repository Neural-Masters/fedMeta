import { useState, useEffect } from 'react'
import { Brain, RefreshCw, TrendingUp, Shield, Globe } from 'lucide-react'
import { apiFetch } from '../services/api'

interface Learning {
  learning_id: string
  title: string
  content: string
  category: string
  confidence: number
  namespace: string
  scope: 'local' | 'federated'
  created_at: string
}

interface SyncStatus {
  last_push: string
  last_pull: string
  total_pushed: number
  total_pulled: number
  pending_count: number
}

export default function LearningTab({ userId }: { userId: string }) {
  const [learnings, setLearnings] = useState<Learning[]>([])
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadLearnings()
    loadSyncStatus()
  }, [userId])

  const loadLearnings = async () => {
    try {
      const res = await apiFetch(`/learning/${encodeURIComponent(userId)}`)
      if (res.ok) setLearnings(await res.json())
    } catch (e) {
      console.error('Failed to load learnings', e)
    }
  }

  const loadSyncStatus = async () => {
    try {
      const res = await apiFetch(`/federated/status/${encodeURIComponent(userId)}`)
      if (res.ok) setSyncStatus(await res.json())
    } catch (e) {
      console.error('Failed to load sync status', e)
    }
  }

  const triggerSync = async () => {
    setLoading(true)
    try {
      const response = await apiFetch(`/federated/sync/${encodeURIComponent(userId)}`, { method: 'POST' })
      if (!response.ok) throw new Error('Federated sync failed')
      await Promise.all([loadLearnings(), loadSyncStatus()])
    } catch (e) {
      console.error('Failed to sync', e)
    }
    setLoading(false)
  }

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      tool_usage: 'bg-blue-500/20 text-blue-400',
      error_handling: 'bg-red-500/20 text-red-400',
      preference: 'bg-green-500/20 text-green-400',
      domain: 'bg-purple-500/20 text-purple-400',
      user_memory: 'bg-amber-500/20 text-amber-300',
      user_profile: 'bg-cyan-500/20 text-cyan-300',
      local: 'bg-gray-500/20 text-gray-300',
    }
    return colors[category] || 'bg-gray-500/20 text-gray-400'
  }

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">Learning Dashboard</h2>
          <p className="text-gray-400 mt-1">Federated learning insights and sync status</p>
        </div>
        <button
          onClick={triggerSync}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 text-white rounded-lg text-sm font-medium"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Syncing...' : 'Sync Now'}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 mb-8">
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <Brain size={14} />
            Local Rules
          </div>
          <p className="text-2xl font-bold text-gray-100">{learnings.filter((item) => item.scope === 'local').length}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <Globe size={14} />
            Federated Rules
          </div>
          <p className="text-2xl font-bold text-gray-100">{learnings.filter((item) => item.scope === 'federated').length}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <TrendingUp size={14} />
            Pushed
          </div>
          <p className="text-2xl font-bold text-gray-100">{syncStatus?.total_pushed || 0}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <Globe size={14} />
            Pulled
          </div>
          <p className="text-2xl font-bold text-gray-100">{syncStatus?.total_pulled || 0}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <Shield size={14} />
            Pending
          </div>
          <p className="text-2xl font-bold text-gray-100">{syncStatus?.pending_count || 0}</p>
        </div>
      </div>

      {/* Sync Info */}
      {syncStatus && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 mb-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Sync Status</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Last Push:</span>{' '}
              <span className="text-gray-300">{syncStatus.last_push ? new Date(syncStatus.last_push).toLocaleString() : 'Never'}</span>
            </div>
            <div>
              <span className="text-gray-500">Last Pull:</span>{' '}
              <span className="text-gray-300">{syncStatus.last_pull ? new Date(syncStatus.last_pull).toLocaleString() : 'Never'}</span>
            </div>
          </div>
        </div>
      )}

      {/* Learnings List */}
      <div className="space-y-3">
        {learnings.map((learning) => (
          <div key={learning.learning_id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getCategoryColor(learning.category)}`}>
                    {learning.category}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs ${learning.scope === 'federated' ? 'bg-purple-500/20 text-purple-300' : 'bg-gray-700 text-gray-300'}`}>
                    {learning.scope === 'federated' ? 'Shared globally' : 'Local only'}
                  </span>
                  <span className="text-xs text-gray-500">
                    {new Date(learning.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="text-gray-100 text-sm font-medium mb-1">{learning.title}</p>
                <p className="text-gray-300 text-sm">{learning.content}</p>
              </div>
              {learning.scope === 'federated' && (
              <div className="ml-4 flex items-center gap-1">
                <div className="w-16 h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full"
                    style={{ width: `${learning.confidence * 100}%` }}
                  />
                </div>
                <span className="text-xs text-gray-500 w-8">{(learning.confidence * 100).toFixed(0)}%</span>
              </div>
              )}
            </div>
          </div>
        ))}
        {learnings.length === 0 && (
          <div className="text-center py-16 text-gray-500">
            <Brain size={48} className="mx-auto mb-4 opacity-50" />
            <p>No learnings yet</p>
            <p className="text-sm mt-1">Learnings will appear as the agent discovers patterns</p>
          </div>
        )}
      </div>
    </div>
  )
}
