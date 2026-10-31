/**
 * Loads the PayPal JS SDK, once per page load.
 *
 * Only the Billing page needs the SDK, so it is injected on demand rather
 * than bundled — and the injected script is keyed by client id, so a
 * sandbox/live switch on the server picks up the right credentials
 * without a stale cached SDK.
 */

interface PayPalButtonsConfig {
  createOrder: () => Promise<string>
  onApprove: (data: { orderID: string }) => Promise<void>
  onError?: (error: unknown) => void
  style?: Record<string, string>
}

interface PayPalSDK {
  Buttons: (config: PayPalButtonsConfig) => {
    render: (target: HTMLElement) => Promise<void>
    close: () => void
  }
}

declare global {
  interface Window {
    paypal?: PayPalSDK
  }
}

const loading: Map<string, Promise<PayPalSDK>> = new Map()

export function loadPayPal(clientId: string): Promise<PayPalSDK> {
  const cached = loading.get(clientId)
  if (cached) return cached

  const promise = new Promise<PayPalSDK>((resolve, reject) => {
    // A previously injected SDK for a different client id is unusable —
    // remove it so the new one can take its place.
    document.querySelectorAll('script[data-paypal-sdk]').forEach(s => s.remove())

    const script = document.createElement('script')
    script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=USD`
    script.async = true
    script.dataset.paypalSdk = clientId
    script.onload = () => {
      if (window.paypal) resolve(window.paypal)
      else reject(new Error('the PayPal SDK loaded but did not initialize'))
    }
    script.onerror = () => {
      loading.delete(clientId)
      reject(new Error('failed to load the PayPal SDK'))
    }
    document.head.appendChild(script)
  })

  loading.set(clientId, promise)
  return promise
}
