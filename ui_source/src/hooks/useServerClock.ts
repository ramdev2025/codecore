import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Clock-skew correction.
 *
 * Every expiry Jupiter reports is an absolute server timestamp. A laptop with
 * a fast clock would render live claims as already expired, and one with a
 * slow clock would show expired claims as live. So we measure the offset
 * between the server's clock and this browser's, and render every countdown
 * against corrected time rather than `Date.now()`.
 *
 * `tick` re-renders once a second so countdowns move without every consumer
 * wiring up its own interval.
 */
export function useServerClock() {
  const offsetRef = useRef(0)
  const [, setTick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setTick(t => (t + 1) % 1_000_000), 1000)
    return () => clearInterval(id)
  }, [])

  /** Feed the `now` field from any server payload to re-sync the offset. */
  const syncFrom = useCallback((serverNow: string | null | undefined) => {
    if (!serverNow) return
    const parsed = Date.parse(serverNow)
    if (Number.isNaN(parsed)) return
    offsetRef.current = parsed - Date.now()
  }, [])

  /** Milliseconds since epoch, corrected to the server's clock. */
  const correctedNow = useCallback(() => Date.now() + offsetRef.current, [])

  return { syncFrom, correctedNow, offsetMs: offsetRef.current }
}
