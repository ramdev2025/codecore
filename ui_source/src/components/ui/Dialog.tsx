import * as RadixDialog from '@radix-ui/react-dialog'
import clsx from 'clsx'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useMediaQuery } from '../../hooks/useMediaQuery'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

/**
 * Radix Dialog with a mobile sheet presentation.
 *
 * Radix is here for the parts that are easy to get wrong by hand: focus trap,
 * focus restore on close, `aria-modal`, Escape handling, and scroll locking.
 *
 * Below 640px it presents as a bottom sheet filling most of the viewport —
 * a centred dialog on a phone leaves unusable slivers of backdrop and puts
 * the close button out of thumb reach.
 */
export function Dialog({ open, onOpenChange, title, description, children, footer }: Props) {
  const isMobile = useMediaQuery('(max-width: 639px)')
  const reduceMotion = useReducedMotion()

  // With reduced motion the panel still appears, it just does not travel.
  const panelMotion = reduceMotion
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.12 } }
    : isMobile
      ? {
          initial: { y: '100%' }, animate: { y: 0 }, exit: { y: '100%' },
          transition: { type: 'spring' as const, damping: 32, stiffness: 320 },
        }
      : {
          initial: { opacity: 0, scale: 0.97, y: 8 },
          animate: { opacity: 1, scale: 1, y: 0 },
          exit: { opacity: 0, scale: 0.97, y: 8 },
          transition: { duration: 0.16 },
        }

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <RadixDialog.Portal forceMount>
            <RadixDialog.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: reduceMotion ? 0.01 : 0.15 }}
              />
            </RadixDialog.Overlay>

            {/* Positioning lives on this wrapper and never on the panel.
                framer-motion writes the panel's `transform` inline for the
                scale/slide, and an inline transform beats Tailwind's
                half-size translate utilities — so centring the panel with a
                left/top 50% plus a negative self-translate puts its top-left
                corner at the viewport centre rather than its middle, as soon
                as the animation touches `transform`. (It looked fine only
                under reduced motion, where the panel animates opacity alone
                and writes no transform at all.) Flexbox owes nothing to
                `transform`, so the two cannot collide.

                `pointer-events-none` keeps the padding around the panel
                click-through to the overlay beneath; the panel re-enables
                them for itself. */}
            <div
              className={clsx(
                'pointer-events-none fixed inset-0 z-50 flex justify-center',
                isMobile ? 'items-end' : 'items-center p-6',
              )}
            >
              <RadixDialog.Content asChild forceMount>
                <motion.div
                  {...panelMotion}
                  className={clsx(
                    'pointer-events-auto flex w-full flex-col bg-ui-surface shadow-elevated focus:outline-none',
                    isMobile
                      ? 'max-h-[92vh] rounded-t-2xl border-t border-ui-border'
                      // max-w rather than a 100vw calc: the wrapper's padding
                      // already reserves the gutter, and 100vw ignores the
                      // scrollbar Radix compensates for while the dialog is open.
                      : 'max-h-[85vh] max-w-[46rem] rounded-2xl border border-ui-border',
                  )}
                >
                  {/* Grab handle doubles as a visual affordance that the sheet dismisses. */}
                  {isMobile && (
                    <div className="flex justify-center pt-2.5" aria-hidden="true">
                      <span className="h-1 w-10 rounded-full bg-ui-border-strong" />
                    </div>
                  )}

                  <div className="flex items-start justify-between gap-3 border-b border-ui-border px-5 py-4">
                    <div className="min-w-0">
                      <RadixDialog.Title className="text-base font-semibold text-ui-text">
                        {title}
                      </RadixDialog.Title>
                      {description && (
                        <RadixDialog.Description className="mt-1 text-sm text-ui-text-2">
                          {description}
                        </RadixDialog.Description>
                      )}
                    </div>
                    <RadixDialog.Close
                      aria-label="Close"
                      className="-mr-1.5 -mt-1.5 flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-ui-text-2 hover:bg-ui-hover hover:text-ui-text focus-visible:ring-2 focus-visible:ring-ui-accent"
                    >
                      <X className="h-5 w-5" />
                    </RadixDialog.Close>
                  </div>

                  <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>

                  {footer && (
                    <div className="border-t border-ui-border px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">
                      {footer}
                    </div>
                  )}
                </motion.div>
              </RadixDialog.Content>
            </div>
          </RadixDialog.Portal>
        )}
      </AnimatePresence>
    </RadixDialog.Root>
  )
}
