import { useState, useEffect } from 'react'
import { Plus, Trash2, Power, PowerOff } from 'lucide-react'

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
      const res = await fetch(`http://localhost:8000/tools/${userId}`)
      if (res.ok) setTools(await res.json())
    } catch (e) {
      console.error('Failed to load tools', e)
    }
  }

  const submitTool = async () => {
    try {
      await fetch(`http://localhost:8000/tools/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          headers: JSON.parse(form.headers || '{}'),
          input_schema: JSON.parse(form.input_schema || '{}'),
          output_schema: JSON.parse(form.output_schema || '{}'),
          tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean),
        }),
      })
      setShowForm(false)
      setForm(emptyForm)
      loadTools()
    } catch (e) {
      console.error('Failed to register tool', e)
    }
  }

  const toggleTool = async (tool: APITool) => {
    try {
      await fetch(`http://localhost:8000/tools/${userId}/${tool.name}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !tool.is_active }),
      })
      loadTools()
    } catch (e) {
      console.error('Failed to toggle tool', e)
    }
  }

  const deleteTool = async (name: string) => {
    if (!confirm(`Delete tool "${name}"?`)) return
    try {
      await fetch(`http://localhost:8000/tools/${userId}/${name}`, { method: 'DELETE' })
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
              <label className="block text-sm text-gray-400 mb-1">Tool Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
                placeholder="e.g., search_docs"
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
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              placeholder="What does this tool do?"
            />
          </div>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Headers (JSON)</label>
              <textarea
                value={form.headers}
                onChange={(e) => setForm({ ...form, headers: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500 h-20 font-mono text-xs"
                placeholder='{"Authorization": "Bearer ..."}'
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Input Schema (JSON)</label>
              <textarea
                value={form.input_schema}
                onChange={(e) => setForm({ ...form, input_schema: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500 h-20 font-mono text-xs"
                placeholder='{"type": "object", "properties": {...}}'
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
