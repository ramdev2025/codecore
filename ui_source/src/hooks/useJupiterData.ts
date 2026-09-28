import { useCallback, useEffect, useRef, useState } from 'react'
import { api, streamUrl, type ActivityOut, type SemanticOut } from '../api/client'

type Connection = 'connecting' | 'live' | 'polling' | 'error'

const POLL_MS = 5000
const SEMANTIC_POLL_MS = 15000

/**
 * Live activity for the signed-in member's org.
 *
 * Prefers the SSE stream; falls back to polling `/api/activity` if the stream
 * errors or never opens, so the dashboard degrades rather than going blank.
 */
export function useJupiterData(apiKey: string | null, syncClock: (now: string | null | undefined) => void) {
  const [activity, setActivity] = useState<ActivityOut | null>(null)
  const [semantic, setSemantic] = useState<SemanticOut | null>(null)
  const [connection, setConnection] = useState<Connection>('connecting')
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const pollRef = useRef<number | null>(null)

  const applyActivity = useCallback((next: ActivityOut) => {
    syncClock(next.now)
    setActivity(next)
    setError(null)
  }, [syncClock])

  const refresh = useCallback(async () => {
    if (!apiKey) return
    try {
      applyActivity(await api.activity())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setConnection('error')
    }
  }, [apiKey, applyActivity])

  const refreshSemantic = useCallback(async () => {
    if (!apiKey) return
    try {
      setSemantic(await api.semantic())
    } catch {
      /* Advisory feature — a failure here must never take the dashboard down. */
    }
  }, [apiKey])

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    if (pollRef.current !== null) return
    setConnection('polling')
    pollRef.current = window.setInterval(() => { void refresh() }, POLL_MS)
  }, [refresh])

  // Initial load + semantic polling.
  useEffect(() => {
    if (!apiKey) return
    void refresh()
    void refreshSemantic()
    const id = window.setInterval(() => { void refreshSemantic() }, SEMANTIC_POLL_MS)
    return () => clearInterval(id)
  }, [apiKey, refresh, refreshSemantic])

  // SSE stream, with polling as the fallback.
  useEffect(() => {
    if (!apiKey || !activity?.slug) return

    const es = new EventSource(streamUrl(activity.slug, apiKey))
    esRef.current = es

    es.onopen = () => {
      stopPolling()
      setConnection('live')
    }
    es.onmessage = (ev) => {
      try {
        applyActivity(JSON.parse(ev.data) as ActivityOut)
        setConnection('live')
      } catch {
        /* a malformed frame is not worth tearing the stream down for */
      }
    }
    es.onerror = () => {
      es.close()
      esRef.current = null
      startPolling()
    }

    return () => {
      es.close()
      esRef.current = null
    }
    // Re-opening on slug change is intended; `activity` itself is not a dep.
  }, [apiKey, activity?.slug, applyActivity, startPolling, stopPolling])

  useEffect(() => stopPolling, [stopPolling])

  return { activity, semantic, connection, error, refresh, refreshSemantic }
}
