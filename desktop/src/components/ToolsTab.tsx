import { useState, useEffect } from 'react'
import { Plus, Trash2, Power, PowerOff } from 'lucide-react'
import { apiFetch } from '../services/api'

interface APITool {
  endpoint_id: string
  name: string
  description: string
  method: string
  url: string
  headers: Record<string, string>
  input_schema: Record<string, any>
  output_schema: Record<string, any>
  is_active: boolean
  tags: string[]
}

export default function ToolsTab({ userId }: { userId: string }) {
  const [tools, setTools] = useState<APITool[]>([])
  const [showForm, setShowForm] = useState(false)
  const [formError, setFormError] = useState('')

  const emptyForm = {
    name: '',
    description: '',
    method: 'GET',
    url: '',
    headers: '{}',
    input_schema: '{}',
    output_schema: '{}',
    tags: '',
  }
  const [form, setForm] = useState(emptyForm)

  useEffect(() => {
    loadTools()
  }, [userId])

  const loadTools = async () => {
    try {
      const res = await apiFetch(`/tools/${encodeURIComponent(userId)}`)
      if (res.ok) setTools(await res.json())
    } catch (e) {
      console.error('Failed to load tools', e)
    }
  }

  const submitTool = async () => {
    setFormError('')
    try {
      const response = await apiFetch(`/tools/${encodeURIComponent(userId)}`, {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          headers: JSON.parse(form.headers || '{}'),
          input_schema: JSON.parse(form.input_schema || '{}'),
          output_schema: JSON.parse(form.output_schema || '{}'),
          tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        }),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Tool registration failed')
      }
      setShowForm(false)
      setForm(emptyForm)
      loadTools()
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Could not register tool')
    }
  }

  const toggleTool = async (tool: APITool) => {
    try {
      const response = await apiFetch(`/tools/${encodeURIComponent(userId)}/${encodeURIComponent(tool.name)}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !tool.is_active }),
      })
      if (!response.ok) throw new Error('Tool update failed')
      loadTools()
    } catch (e) {
      console.error('Failed to toggle tool', e)
    }
  }

  const deleteTool = async (name: string) => {
    if (!confirm(`Delete tool "${name}"?`)) return
    try {
      const response = await apiFetch(`/tools/${encodeURIComponent(userId)}/${encodeURIComponent(name)}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Tool deletion failed')
      loadTools()
    } catch (e) {
      console.error('Failed to delete tool', e)
    }
  }

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">API Tools</h2>
          <p className="text-gray-400 mt-1">Register API endpoints for the agent to use</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
        >
          <Plus size={16} />
          Register Tool
        </button>
      </div>

      {/* Registration Form */}
      {showForm && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-6">
          <h3 className="text-lg font-semibold text-gray-200 mb-4">Register New API Endpoint</h3>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Tool Name (Agno function name)</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
                placeholder="e.g., web_search"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">HTTP Method</label>
              <select
                value={form.method}
                onChange={(e) => setForm({ ...form, method: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              >
                {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">URL</label>
            <input
              type="text"
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              placeholder="https://api.example.com/endpoint"
            />
          </div>
          <div className="mb-4">
              <label className="block text-sm text-gray-400 mb-1">Description (tell the agent when to call it)</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              placeholder="Search the web for current information matching a query and return the top results."
            />
          </div>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Headers (JSON; use environment placeholders for secrets)</label>
              <textarea
                value={form.headers}
                onChange={(e) => setForm({ ...form, headers: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500 h-20 font-mono text-xs"
                placeholder='{"Authorization": "Bearer ${WEB_SEARCH_API_TOKEN}", "Content-Type": "application/json"}'
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Input Schema (JSON)</label>
              <textarea
                value={form.input_schema}
                onChange={(e) => setForm({ ...form, input_schema: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500 h-20 font-mono text-xs"
                placeholder='{"type":"object","properties":{"query":{"type":"string","description":"Search query"}},"required":["query"],"additionalProperties":false}'
              />
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-1">Tags (comma-separated)</label>
            <input
              type="text"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              placeholder="search, docs, api"
            />
          </div>
          <p className="mb-4 text-xs text-gray-500">
            FedMeta creates an Agno-compatible Python callable for this endpoint and gives Agno the JSON input schema. Keep credentials in the backend environment, not in this form.
          </p>
          {formError && <p role="alert" className="mb-4 text-sm text-red-300">{formError}</p>}
          <div className="flex gap-2">
            <button
              onClick={submitTool}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
            >
              Register
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg text-sm font-medium"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Tools List */}
      <div className="space-y-3">
        {tools.map((tool) => (
          <div key={tool.endpoint_id} className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex items-center gap-4">
            <div className={`w-2 h-2 rounded-full ${tool.is_active ? 'bg-green-500' : 'bg-gray-600'}`} />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-100">{tool.name}</span>
                <span className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-400">{tool.method}</span>
              </div>
              <p className="text-sm text-gray-400 mt-0.5">{tool.description || 'No description'}</p>
              <p className="text-xs text-gray-500 mt-0.5 font-mono">{tool.url}</p>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => toggleTool(tool)}
                className={`p-2 rounded-lg ${tool.is_active ? 'text-green-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-700'}`}
                title={tool.is_active ? 'Deactivate' : 'Activate'}
              >
                {tool.is_active ? <Power size={16} /> : <PowerOff size={16} />}
              </button>
              <button
                onClick={() => deleteTool(tool.name)}
                className="p-2 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded-lg"
                title="Delete"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
        {tools.length === 0 && !showForm && (
          <div className="text-center py-16 text-gray-500">
            <Wrench size={48} className="mx-auto mb-4 opacity-50" />
            <p>No tools registered yet</p>
            <p className="text-sm mt-1">Register an API endpoint to get started</p>
          </div>
        )}
      </div>
    </div>
  )
}

function Wrench(props: any) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={props.className}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  )
}
