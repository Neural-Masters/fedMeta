import { useState, useEffect } from 'react'
import { Save } from 'lucide-react'

interface Profile {
  name: string
  role: string
  expertise_level: string
  communication_style: string
  preferred_format: string
  domains: string[]
  custom_rules: Record<string, string>
}

const defaultProfile: Profile = {
  name: '',
  role: '',
  expertise_level: 'intermediate',
  communication_style: 'detailed',
  preferred_format: 'paragraphs',
  domains: [],
  custom_rules: {},
}

const expertiseLevels = ['beginner', 'intermediate', 'advanced', 'expert']
const communicationStyles = ['concise', 'detailed', 'technical', 'friendly']
const responseFormats = ['bullet_points', 'paragraphs', 'step_by_step', 'code_heavy']

export default function ProfileTab({ userId }: { userId: string }) {
  const [profile, setProfile] = useState<Profile>(defaultProfile)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadProfile()
  }, [userId])

  const loadProfile = async () => {
    try {
      const res = await fetch(`http://localhost:8000/profile/${userId}`)
      if (res.ok) {
        const data = await res.json()
        setProfile(data)
      }
    } catch (e) {
      console.log('No existing profile, using defaults')
    }
  }

  const saveProfile = async () => {
    setLoading(true)
    try {
      await fetch(`http://localhost:8000/profile/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Failed to save profile', e)
    }
    setLoading(false)
  }

  const addDomain = () => {
    setProfile({ ...profile, domains: [...profile.domains, ''] })
  }

  const updateDomain = (index: number, value: string) => {
    const domains = [...profile.domains]
    domains[index] = value
    setProfile({ ...profile, domains })
  }

  const removeDomain = (index: number) => {
    setProfile({ ...profile, domains: profile.domains.filter((_, i) => i !== index) })
  }

  const addRule = () => {
    setProfile({ ...profile, custom_rules: { ...profile.custom_rules, '': '' } })
  }

  const updateRule = (key: string, newKey: string, value: string) => {
    const rules = { ...profile.custom_rules }
    if (key !== newKey) {
      delete rules[key]
    }
    rules[newKey] = value
    setProfile({ ...profile, custom_rules: rules })
  }

  const removeRule = (key: string) => {
    const rules = { ...profile.custom_rules }
    delete rules[key]
    setProfile({ ...profile, custom_rules: rules })
  }

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-gray-100">User Profile</h2>
          <p className="text-gray-400 mt-1">Configure how the agent adapts to your needs</p>
        </div>
        <button
          onClick={saveProfile}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Save size={16} />
          {loading ? 'Saving...' : saved ? 'Saved!' : 'Save Profile'}
        </button>
      </div>

      <div className="space-y-6">
        {/* Basic Info */}
        <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h3 className="text-lg font-semibold text-gray-200 mb-4">Basic Information</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={profile.name}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
                placeholder="Your name"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Role</label>
              <input
                type="text"
                value={profile.role}
                onChange={(e) => setProfile({ ...profile, role: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
                placeholder="e.g., Software Engineer"
              />
            </div>
          </div>
        </section>

        {/* Agent Behavior */}
        <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <h3 className="text-lg font-semibold text-gray-200 mb-4">Agent Behavior</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Expertise Level</label>
              <select
                value={profile.expertise_level}
                onChange={(e) => setProfile({ ...profile, expertise_level: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              >
                {expertiseLevels.map((l) => (
                  <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Communication Style</label>
              <select
                value={profile.communication_style}
                onChange={(e) => setProfile({ ...profile, communication_style: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              >
                {communicationStyles.map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Response Format</label>
              <select
                value={profile.preferred_format}
                onChange={(e) => setProfile({ ...profile, preferred_format: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 focus:outline-none focus:border-blue-500"
              >
                {responseFormats.map((f) => (
                  <option key={f} value={f}>{f.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Domains */}
        <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-200">Domains of Interest</h3>
            <button onClick={addDomain} className="text-sm text-blue-400 hover:text-blue-300">+ Add</button>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.domains.map((domain, i) => (
              <div key={i} className="flex items-center gap-1 bg-gray-700 rounded-lg px-3 py-1">
                <input
                  type="text"
                  value={domain}
                  onChange={(e) => updateDomain(i, e.target.value)}
                  className="bg-transparent text-gray-100 text-sm focus:outline-none w-24"
                />
                <button onClick={() => removeDomain(i)} className="text-gray-500 hover:text-red-400">&times;</button>
              </div>
            ))}
            {profile.domains.length === 0 && (
              <p className="text-gray-500 text-sm">No domains added</p>
            )}
          </div>
        </section>

        {/* Custom Rules */}
        <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-200">Custom Rules</h3>
            <button onClick={addRule} className="text-sm text-blue-400 hover:text-blue-300">+ Add Rule</button>
          </div>
          <div className="space-y-2">
            {Object.entries(profile.custom_rules).map(([key, value], index) => (
              <div key={`rule-${index}`} className="flex items-center gap-2">
                <input
                  type="text"
                  value={key}
                  onChange={(e) => updateRule(key, e.target.value, value)}
                  className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 text-sm focus:outline-none focus:border-blue-500"
                  placeholder="Rule name"
                />
                <input
                  type="text"
                  value={value}
                  onChange={(e) => updateRule(key, key, e.target.value)}
                  className="flex-[2] px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-100 text-sm focus:outline-none focus:border-blue-500"
                  placeholder="Rule value"
                />
                <button onClick={() => removeRule(key)} className="text-gray-500 hover:text-red-400">&times;</button>
              </div>
            ))}
            {Object.keys(profile.custom_rules).length === 0 && (
              <p className="text-gray-500 text-sm">No custom rules defined</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
