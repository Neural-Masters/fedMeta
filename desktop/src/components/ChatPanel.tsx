import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Loader2, Sparkles, History } from 'lucide-react'
import { apiFetch } from '../services/api'

interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export default function ChatPanel({ userId }: { userId: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const chatRequestRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    chatRequestRef.current?.abort()
    chatRequestRef.current = null
    setStreamingMessageId(null)
    setLoading(false)
    setMessages([])
    setHistoryError('')
    setHistoryLoading(true)

    apiFetch(`/agent/history/${encodeURIComponent(userId)}?last_n_runs=50`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'Could not load conversation history')
        const restored = Array.isArray(data.messages)
          ? data.messages.filter(
              (message: Message) =>
                (message.role === 'user' || message.role === 'assistant') &&
                typeof message.content === 'string',
            )
          : []
        setMessages(restored)
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) {
          setHistoryError(error.message || 'Could not load conversation history')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false)
      })

    return () => controller.abort()
  }, [userId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    return () => {
      chatRequestRef.current?.abort()
    }
  }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading || historyLoading) return

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }
    const assistantId = `assistant-${Date.now()}`
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: 'assistant', content: '', timestamp: new Date().toISOString() },
    ])
    setInput('')
    setLoading(true)
    setStreamingMessageId(assistantId)
    const controller = new AbortController()
    chatRequestRef.current = controller

    try {
      const res = await apiFetch('/agent/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: userMessage.content }),
        signal: controller.signal,
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'The agent could not complete the request')
      }
      if (!res.body) throw new Error('The server did not open a streaming response')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let responseText = ''

      const handleEvent = (block: string) => {
        let eventName = 'message'
        const dataLines: string[] = []
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) eventName = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
        }
        if (dataLines.length === 0) return
        const payload = JSON.parse(dataLines.join('\n'))
        if (eventName === 'error') throw new Error(payload.detail || 'The agent run failed')
        if (eventName === 'token' && typeof payload.content === 'string') {
          responseText += payload.content
          setMessages((prev) => prev.map((message) =>
            message.id === assistantId ? { ...message, content: responseText } : message,
          ))
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
        let boundary = buffer.indexOf('\n\n')
        while (boundary >= 0) {
          handleEvent(buffer.slice(0, boundary))
          buffer = buffer.slice(boundary + 2)
          boundary = buffer.indexOf('\n\n')
        }
      }
      buffer += decoder.decode()
      if (buffer.trim()) handleEvent(buffer)
      if (!responseText) {
        setMessages((prev) => prev.map((message) =>
          message.id === assistantId ? { ...message, content: 'The agent returned an empty response.' } : message,
        ))
      }
      setStreamingMessageId(null)
    } catch (error) {
      if (controller.signal.aborted) return
      const detail = error instanceof Error ? error.message : 'Unknown error'
      setMessages((prev) => prev.map((message) =>
        message.id === assistantId
          ? { ...message, content: `Error: ${detail}. Make sure the backend is running and try again.` }
          : message,
      ))
      setStreamingMessageId(null)
    } finally {
      if (chatRequestRef.current === controller) {
        chatRequestRef.current = null
        setLoading(false)
      }
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 bg-gray-800/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Bot size={20} className="text-white" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-100">FedMeta Agent</h2>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <History size={12} />
              Saved conversation · {userId}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-xs text-gray-500">Online</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {historyLoading && messages.length === 0 && (
          <div className="flex items-center justify-center gap-2 py-16 text-gray-500">
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Loading saved conversation…</span>
          </div>
        )}
        {!historyLoading && historyError && messages.length === 0 && (
          <div className="mx-auto max-w-md rounded-xl border border-amber-700/40 bg-amber-900/20 p-4 text-center text-sm text-amber-200">
            {historyError} — you can still send a message.
          </div>
        )}
        {!historyLoading && messages.length === 0 && (
          <div className="text-center py-16 text-gray-500 animate-fade-in">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-600/20 flex items-center justify-center mx-auto mb-4">
              <Sparkles size={32} className="text-blue-400" />
            </div>
            <p className="text-lg font-medium text-gray-300">Start a conversation</p>
            <p className="text-sm mt-1">The agent adapts to your profile and uses your registered tools</p>
          </div>
        )}
        {messages.map((msg, i) => {
          if (msg.role === 'assistant' && msg.id === streamingMessageId && !msg.content) return null
          const showStreamingCursor = loading && msg.id === streamingMessageId

          return (
            <div
              key={msg.id || i}
              className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-in`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-md">
                  <Bot size={16} className="text-white" />
                </div>
              )}
              <div
                className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-md shadow-blue-600/20'
                    : 'bg-gray-800 text-gray-200 border border-gray-700 shadow-md'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {showStreamingCursor && (
                  <span className="inline-block w-1.5 h-4 bg-blue-400 ml-0.5 animate-pulse" />
                )}
                <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-blue-200' : 'text-gray-500'}`}>
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </p>
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-gray-700 flex items-center justify-center flex-shrink-0">
                  <User size={16} className="text-gray-300" />
                </div>
              )}
            </div>
          )
        })}
        {loading && (!streamingMessageId || !messages.some((message) => message.id === streamingMessageId && message.content)) && (
          <div className="flex gap-3 animate-slide-in">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-md">
              <Bot size={16} className="text-white" />
            </div>
            <div className="bg-gray-800 rounded-2xl px-4 py-3 border border-gray-700 shadow-md">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-700 bg-gray-800/80 backdrop-blur-sm">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl text-gray-100 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 resize-none transition-all"
            placeholder="Type your message..."
            rows={1}
          />
          <button
            onClick={sendMessage}
            disabled={loading || historyLoading || !input.trim()}
            className="px-4 py-3 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 disabled:from-gray-700 disabled:to-gray-700 disabled:text-gray-500 text-white rounded-xl transition-all shadow-md shadow-blue-600/20 disabled:shadow-none"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
