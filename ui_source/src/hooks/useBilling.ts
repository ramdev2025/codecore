import { useCallback, useEffect, useState } from 'react'
import { api, type BillingOut } from '../api/client'

/**
 * Billing state for the org: wallet balance, current plan, cycle end,
 * team count, and the PayPal availability block.
 *
 * Fetches on mount and exposes `refresh` for after a top-up, redeem, or
 * team change. No polling: billing state changes only through actions
 * taken on this page (or the Team page), each of which refreshes.
 */
export function useBilling(enabled: boolean) {
  const [billing, setBilling] = useState<BillingOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setBilling(await api.billing())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    if (enabled) void refresh()
  }, [enabled, refresh])

  return { billing, error, refresh }
}
