import * as RadixDialog from '@radix-ui/react-dialog'
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

            <RadixDialog.Content asChild forceMount>
              <motion.div
                {...panelMotion}
                className={
                  isMobile
                    ? 'fixed inset-x-0 bottom-0 z-50 flex max-h-[92vh] flex-col rounded-t-2xl border-t border-ui-border bg-ui-surface shadow-elevated focus:outline-none'
                    : 'fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[min(46rem,calc(100vw-3rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-ui-border bg-ui-surface shadow-elevated focus:outline-none'
                }
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
          </RadixDialog.Portal>
        )}
      </AnimatePresence>
    </RadixDialog.Root>
  )
}
