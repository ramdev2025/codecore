import { useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { ChevronLeft, ChevronRight, Menu, User, X } from 'lucide-react'
import { ThemeSwitcher } from './ui/ThemeSwitcher'
import { useMediaQuery } from '../hooks/useMediaQuery'
import clsx from 'clsx'

interface NavItem { label: string; icon: ReactNode; id: string; children?: string[] }
interface BreadcrumbItem { label: string; onClick?: () => void }
interface Props {
  navItems: NavItem[]; activePage: string; onNavigate: (id: string) => void
  appName: string; appIcon?: ReactNode; children: ReactNode
  breadcrumbs?: BreadcrumbItem[]; userDisplayName?: string; collapsible?: boolean
  headerAccessory?: ReactNode
  /** Per-nav-item counts, e.g. unresolved conflicts on Log. */
  badges?: Record<string, number>
}

/**
 * Three navigation presentations, by width:
 *   ≥980px  fixed sidebar, collapsible to icons
 *   640–979 overlay drawer behind a menu button
 *   <640px  bottom tab bar — thumb-reachable, no drawer to open
 *
 * A drawer on a phone means two taps to change page and a hidden information
 * architecture; a tab bar is one tap and always visible.
 */
export function DashShell({
  navItems, activePage, onNavigate, appName, appIcon, children,
  breadcrumbs, userDisplayName, collapsible = true, headerAccessory, badges,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const isPhone = useMediaQuery('(max-width: 639px)')
  const isTablet = useMediaQuery('(min-width: 640px) and (max-width: 979px)')
  const reduceMotion = useReducedMotion()
  const isActive = (item: NavItem) => item.id === activePage || (item.children ?? []).includes(activePage)

  useEffect(() => { if (!isTablet) setDrawerOpen(false) }, [isTablet])

  const showLabels = isTablet ? true : !collapsed

  const sidebar = (
    <aside
      className={clsx(
        'flex flex-col bg-ui-surface border-r border-ui-border flex-shrink-0',
        isTablet ? 'fixed inset-y-0 left-0 z-40 w-64 shadow-elevated' : (collapsed ? 'w-14' : 'w-56'),
        !isTablet && 'transition-all duration-200',
      )}
      aria-label="Main navigation"
    >
      <div className={clsx('h-12 flex items-center border-b border-ui-border flex-shrink-0', showLabels ? 'px-4 gap-2' : 'justify-center')}>
        {appIcon && <span className="flex-shrink-0 text-ui-accent w-5 h-5">{appIcon}</span>}
        {showLabels && <span className="font-semibold text-ui-text text-sm truncate">{appName}</span>}
        {isTablet && (
          <button onClick={() => setDrawerOpen(false)} aria-label="Close navigation"
            className="ml-auto w-11 h-11 -mr-2 flex items-center justify-center rounded-md text-ui-text-2 hover:bg-ui-hover hover:text-ui-text">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>
      <nav className="flex-1 py-2 overflow-y-auto px-1 space-y-0.5">
        {navItems.map(item => {
          const active = isActive(item)
          const count = badges?.[item.id] ?? 0
          return (
            <button key={item.id} onClick={() => { onNavigate(item.id); setDrawerOpen(false) }}
              title={showLabels ? undefined : item.label}
              aria-current={active ? 'page' : undefined}
              className={clsx('w-full flex items-center gap-3 px-3 h-11 text-sm font-medium transition-colors rounded-md',
                active ? 'bg-ui-accent/10 text-ui-accent' : 'text-ui-text-2 hover:bg-ui-hover hover:text-ui-text',
                !showLabels && 'justify-center')}>
              <span className="flex-shrink-0 w-4 h-4 relative">
                {item.icon}
                {!showLabels && count > 0 && (
                  <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-ui-error" aria-hidden="true" />
                )}
              </span>
              {showLabels && <span className="truncate">{item.label}</span>}
              {showLabels && count > 0 && (
                <span className="ml-auto inline-flex min-w-[1.25rem] justify-center rounded-full bg-ui-error-bg px-1.5 text-xs font-semibold text-ui-error">
                  {count}
                </span>
              )}
              {showLabels && count === 0 && active && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-ui-accent flex-shrink-0" />}
            </button>
          )
        })}
      </nav>
      <div className="border-t border-ui-border py-2 px-1 flex flex-col gap-1 flex-shrink-0">
        <div className={clsx('flex items-center', showLabels ? 'justify-between px-2' : 'justify-center')}>
          {showLabels && <span className="text-xs text-ui-text-2">Theme</span>}
          <ThemeSwitcher compact />
        </div>
        {collapsible && !isTablet && (
          <button onClick={() => setCollapsed(v => !v)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="flex items-center justify-center w-full h-9 text-ui-text-2 hover:text-ui-text hover:bg-ui-hover rounded-md text-xs gap-1">
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <><ChevronLeft className="w-3.5 h-3.5" /><span>Collapse</span></>}
          </button>
        )}
      </div>
    </aside>
  )

  return (
    <div className="flex h-screen bg-ui-bg overflow-hidden">
      {!isPhone && (!isTablet || drawerOpen) && sidebar}

      <AnimatePresence>
        {isTablet && drawerOpen && (
          <motion.div
            className="fixed inset-0 z-30 bg-black/40"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0.01 : 0.15 }}
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <header className="h-12 flex items-center justify-between px-3 sm:px-4 gap-3 border-b border-ui-border bg-ui-surface flex-shrink-0">
          {isTablet && (
            <button onClick={() => setDrawerOpen(true)} aria-label="Open navigation"
              className="w-11 h-11 -ml-2 flex items-center justify-center rounded-md hover:bg-ui-hover text-ui-text-2 flex-shrink-0">
              <Menu className="w-5 h-5" />
            </button>
          )}
          {isPhone && appIcon && (
            <span className="flex-shrink-0 text-ui-accent w-5 h-5" aria-hidden="true">{appIcon}</span>
          )}
          <nav className="flex items-center gap-1 text-sm flex-1 min-w-0" aria-label="Breadcrumb">
            {(breadcrumbs ?? [{ label: appName }]).map((bc, i, arr) => (
              <span key={i} className={clsx('flex items-center gap-1 min-w-0', isPhone && i < arr.length - 1 && 'hidden')}>
                {i > 0 && !isPhone && <ChevronRight className="w-3.5 h-3.5 text-ui-text-2 flex-shrink-0" />}
                {bc.onClick
                  ? <button onClick={bc.onClick} className="text-ui-accent hover:underline truncate">{bc.label}</button>
                  : <span className={clsx('truncate', i === arr.length - 1 ? 'text-ui-text font-medium' : 'text-ui-text-2')}>{bc.label}</span>
                }
              </span>
            ))}
          </nav>
          <div className="flex items-center gap-2 flex-shrink-0">
            {headerAccessory}
            {isPhone && <ThemeSwitcher compact />}
            <div className="w-8 h-8 rounded-full bg-ui-accent flex items-center justify-center text-ui-on-accent text-xs font-semibold"
              title={userDisplayName ?? undefined}>
              {userDisplayName ? userDisplayName.slice(0, 2).toUpperCase() : <User className="w-4 h-4" />}
            </div>
          </div>
        </header>

        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          {children}
        </div>

        {isPhone && (
          <nav
            className="flex-shrink-0 border-t border-ui-border bg-ui-surface pb-[env(safe-area-inset-bottom)]"
            aria-label="Main navigation"
          >
            <ul className="flex">
              {navItems.map(item => {
                const active = isActive(item)
                const count = badges?.[item.id] ?? 0
                return (
                  <li key={item.id} className="flex-1">
                    <button
                      onClick={() => onNavigate(item.id)}
                      aria-current={active ? 'page' : undefined}
                      className={clsx(
                        'w-full min-h-[56px] flex flex-col items-center justify-center gap-0.5 px-1 py-1.5',
                        active ? 'text-ui-accent' : 'text-ui-text-2',
                      )}
                    >
                      <span className="relative w-5 h-5 flex items-center justify-center">
                        {item.icon}
                        {count > 0 && (
                          <span className="absolute -top-0.5 -right-1.5 min-w-[1rem] rounded-full bg-ui-error px-1 text-[10px] font-semibold leading-4 text-white">
                            {count}
                          </span>
                        )}
                      </span>
                      <span className="text-[10px] font-medium leading-none">{item.label}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </nav>
        )}
      </div>
    </div>
  )
}
