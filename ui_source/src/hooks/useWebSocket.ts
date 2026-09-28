import { useEffect, useRef, useCallback } from 'react'
import { create } from 'zustand'

export interface WSMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  toolCalls?: string[]
}

interface WSState {
  messages: WSMessage[]
  isConnected: boolean
  isLoading: boolean
  addMessage: (msg: WSMessage) => void
  appendToLast: (chunk: string) => void
  setLastContent: (content: string) => void
  appendToolCall: (name: string) => void
  finalizeLast: () => void
  clearMessages: () => void
  setConnected: (v: boolean) => void
  setLoading: (v: boolean) => void
}

export const useWSStore = create<WSState>((set) => ({
  messages: [],
  isConnected: false,
  isLoading: false,
  addMessage: (msg) => set(s => ({ messages: [...s.messages, msg] })),
  appendToLast: (chunk) => set(s => {
    const msgs = [...s.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') msgs[msgs.length - 1] = { ...last, content: last.content + chunk }
    return { messages: msgs }
  }),
  setLastContent: (content) => set(s => {
    const msgs = [...s.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') msgs[msgs.length - 1] = { ...last, content }
    return { messages: msgs }
  }),
  appendToolCall: (name) => set(s => {
    const msgs = [...s.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') msgs[msgs.length - 1] = { ...last, toolCalls: [...(last.toolCalls ?? []), name] }
    return { messages: msgs }
  }),
  finalizeLast: () => set(s => {
    const msgs = [...s.messages]
    const last = msgs[msgs.length - 1]
    if (last?.role === 'assistant') msgs[msgs.length - 1] = { ...last, isStreaming: false }
    return { messages: msgs }
  }),
  clearMessages: () => set({ messages: [] }),
  setConnected: (isConnected) => set({ isConnected }),
  setLoading: (isLoading) => set({ isLoading }),
}))

export function useWebSocket(sessionId: string) {
  const store = useWSStore()
  const wsRef = useRef<WebSocket | null>(null)
  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/${sessionId}`)
    wsRef.current = ws
    ws.onopen = () => store.setConnected(true)
    ws.onclose = () => { store.setConnected(false); store.setLoading(false) }
    let hasTokens = false
    ws.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      if (ev.type === 'token' && ev.content) { hasTokens = true; store.appendToLast(ev.content) }
      else if (ev.type === 'tool_call' && ev.name) store.appendToolCall(ev.name)
      else if (ev.type === 'agent' && ev.content && !hasTokens) store.setLastContent(ev.content)
      else if (ev.type === 'complete') { hasTokens = false; store.finalizeLast(); store.setLoading(false) }
      else if (ev.type === 'error') { hasTokens = false; store.finalizeLast(); store.setLoading(false) }
    }
    return () => ws.close()
  }, [sessionId]) // eslint-disable-line react-hooks/exhaustive-deps
  const send = useCallback((query: string) => {
    if (!query.trim() || !store.isConnected || store.isLoading) return
    store.addMessage({ id: crypto.randomUUID(), role: 'user', content: query })
    store.addMessage({ id: crypto.randomUUID(), role: 'assistant', content: '', isStreaming: true })
    store.setLoading(true)
    wsRef.current?.send(JSON.stringify({ query }))
  }, [store])
  return { ...store, send }
}
