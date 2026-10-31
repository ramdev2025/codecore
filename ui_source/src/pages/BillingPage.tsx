import { useEffect, useMemo, useRef, useState } from 'react'
import { CalendarClock, Check, Moon, Sparkles, Users, Wallet } from 'lucide-react'
import { api, type BillingOut, type PlanInfo } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Alert, Button, Card, Input, Spinner } from '../components/ui'
import { useBilling } from '../hooks/useBilling'
import { useToast } from '../hooks/useToast'
import { loadPayPal } from '../lib/loadPayPal'

interface Props {
  active: boolean
}

const PRESETS = [50, 100, 300]

/**
 * The wallet and the plans it buys.
 *
 * Everything on this page degrades: with PayPal unconfigured the top-up
 * card shows the reason instead of the buttons, and the plans still
 * render (an org that already holds points can still redeem).
 */
export function BillingPage({ active }: Props) {
  const { billing, error, refresh } = useBilling(active)
  const toast = useToast(s => s.show)

  const [amount, setAmount] = useState<string>('50')
  const [redeeming, setRedeeming] = useState<string | null>(null)
  const buttonHost = useRef<HTMLDivElement | null>(null)

  const parsedAmount = Number.parseInt(amount, 10)
  const amountValid = Number.isInteger(parsedAmount) && parsedAmount >= 1 && parsedAmount <= 10_000

  const paypalEnabled = billing?.paypal.enabled === true
  const paypalClientId = billing?.paypal.client_id ?? null

  // Render the PayPal buttons once the SDK is available for this client
  // id. Re-rendered (via the key change on the host div) whenever the
  // chosen amount changes, so createOrder picks up the current value.
  useEffect(() => {
    if (!active || !paypalEnabled || !paypalClientId) return
    let cancelled = false
    let close: (() => void) | null = null

    void loadPayPal(paypalClientId)
      .then(sdk => {
        if (cancelled || !buttonHost.current) return
        const buttons = sdk.Buttons({
          createOrder: async () => {
            if (!amountValid) throw new Error('enter a whole-dollar amount between 1 and 10,000')
            const order = await api.createTopup(parsedAmount)
            return order.paypal_order_id
          },
          onApprove: async data => {
            try {
              const result = await api.captureTopup(data.orderID)
              toast(
                result.points_added > 0
                  ? `${result.points_added} Moon Points added — balance is now ${result.balance}`
                  : `This order was already credited — balance is ${result.balance}`,
                'success',
              )
              void refresh()
            } catch (e) {
              toast(e instanceof Error ? e.message : String(e), 'error')
            }
          },
          onError: err => {
            toast(String(err), 'error')
          },
        })
        void buttons.render(buttonHost.current).then(() => {
          close = () => void buttons.close()
        })
      })
      .catch(e => toast(e instanceof Error ? e.message : String(e), 'error'))

    return () => {
      cancelled = true
      if (close) close()
    }
  }, [active, paypalEnabled, paypalClientId, amountValid, parsedAmount, refresh, toast])

  const redeem = async (key: string) => {
    setRedeeming(key)
    try {
      await api.redeem(key)
      const next = await api.billing()
      toast(`${next.plan_label} plan active${next.period_ends_at ? ` until ${new Date(next.period_ends_at).toLocaleDateString()}` : ''}`, 'success')
      void refresh()
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      setRedeeming(null)
    }
  }

  if (error && !billing) {
    return (
      <>
        <PageHeader title="Billing" subtitle="Moon Points and plans" />
        <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
          <Alert variant="error" title="Billing unavailable" message={error} />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Billing" subtitle="Moon Points and plans" />
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {!billing ? (
          <Spinner label="Loading billing…" />
        ) : (
          <div className="grid gap-6 xl:grid-cols-2 items-start">
            <section className="rounded-xl border border-ui-border bg-ui-surface p-5 shadow-card" aria-labelledby="wallet-heading">
              <div className="flex items-center justify-between mb-4">
                <h2 id="wallet-heading" className="text-sm font-semibold text-ui-text flex items-center gap-2">
                  <Wallet className="w-4 h-4 text-ui-accent" aria-hidden="true" />
                  Moon Points wallet
                </h2>
                <StatusBadge label={billing.plan_label} variant={billing.plan === 'free' ? 'neutral' : 'purple'} />
              </div>

              <div className="flex items-end gap-3 mb-1">
                <p className="text-4xl font-bold text-ui-text tabular-nums">{billing.balance}</p>
                <p className="text-sm text-ui-text-2 mb-1">Moon Points</p>
              </div>
              <p className="text-xs text-ui-text-2 mb-4">1 Moon Point = 1 USD. Points never expire.</p>

              <div className="flex items-center gap-2 text-sm text-ui-text-2 mb-5">
                <CalendarClock className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                {billing.plan === 'free'
                  ? 'Free plan — no cycle to renew.'
                  : billing.period_ends_at
                    ? `${billing.plan_label} renews on ${new Date(billing.period_ends_at).toLocaleDateString()} for ${billing.price_points} points.`
                    : '—'}
              </div>

              <h3 className="text-sm font-semibold text-ui-text mb-2">Top up</h3>
              {paypalEnabled ? (
                <>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {PRESETS.map(p => (
                      <Button key={p} variant={parsedAmount === p ? 'primary' : 'secondary'} size="sm"
                        onClick={() => setAmount(String(p))}>
                        {p}
                      </Button>
                    ))}
                  </div>
                  <div className="max-w-[200px] mb-4">
                    <Input
                      label="Custom amount (USD)"
                      inputMode="numeric"
                      value={amount}
                      onChange={e => setAmount(e.target.value)}
                      error={amount && !amountValid ? 'Whole dollars between 1 and 10,000' : undefined}
                      hint={amountValid ? `${parsedAmount} Moon Points` : undefined}
                    />
                  </div>
                  {/* Keyed by amount: the PayPal buttons are re-created when
                      the amount changes so createOrder uses the current value. */}
                  <div key={amount} ref={buttonHost} aria-label="PayPal checkout" />
                </>
              ) : (
                <Alert variant="info" title="Top-ups unavailable" message={billing.paypal.reason ?? 'PayPal is not configured on this deployment.'} />
              )}
            </section>

            <PlansSection billing={billing} redeeming={redeeming} onRedeem={redeem} />
          </div>
        )}
      </div>
    </>
  )
}

function PlansSection({ billing, redeeming, onRedeem }: {
  billing: BillingOut
  redeeming: string | null
  onRedeem: (key: string) => void
}) {
  const currentPlan = billing.plan
  return (
    <section aria-labelledby="plans-heading">
      <h2 id="plans-heading" className="text-sm font-semibold text-ui-text mb-3">
        Plans — 30-day cycles
      </h2>
      <div className="grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
        {billing.plans.map(plan => (
          <PlanCard key={plan.key} plan={plan} current={plan.key === currentPlan}
            balance={billing.balance} loading={redeeming === plan.key} onRedeem={onRedeem} />
        ))}
      </div>
      <p className="text-xs text-ui-text-2 mt-3">
        Redeeming extends your current cycle. When a cycle ends, the next one is charged
        automatically from the balance — an empty balance drops the org to Free (existing
        developer teams are kept).
      </p>
    </section>
  )
}

function PlanCard({ plan, current, balance, loading, onRedeem }: {
  plan: PlanInfo
  current: boolean
  balance: number
  loading: boolean
  onRedeem: (key: string) => void
}) {
  const isFree = plan.price_points === 0
  const affordable = balance >= plan.price_points
  return (
    <Card className={current ? 'ring-2 ring-ui-accent' : undefined}>
      <div className="flex items-start justify-between gap-2 mb-1">
        <h3 className="text-sm font-semibold text-ui-text">{plan.label}</h3>
        {current && <StatusBadge label="current" variant="success" icon={<Check className="w-3 h-3" />} />}
      </div>
      <p className="text-2xl font-bold text-ui-text mb-1">
        {plan.price_points === 0 ? 'Free' : plan.price_points}
        {!isFree && <span className="text-sm font-normal text-ui-text-2 ml-1">points / cycle</span>}
      </p>
      <p className="flex items-center gap-1.5 text-xs text-ui-text-2 mb-4">
        <Users className="w-3.5 h-3.5" aria-hidden="true" />
        up to {plan.max_teams} developer {plan.max_teams === 1 ? 'team' : 'teams'}
      </p>
      {!isFree && !current && (
        <Button
          size="sm"
          variant={affordable ? 'primary' : 'secondary'}
          icon={<Sparkles className="w-3.5 h-3.5" />}
          disabled={!affordable}
          loading={loading}
          onClick={() => onRedeem(plan.key)}
        >
          {affordable ? 'Redeem' : `Needs ${plan.price_points - balance} more`}
        </Button>
      )}
    </Card>
  )
}
