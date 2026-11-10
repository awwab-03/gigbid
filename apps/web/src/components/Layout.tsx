import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { DegradedBanner } from './DegradedBanner'

const NAV = [
  ['/inbox', 'Job inbox'], ['/approvals', 'Approvals'], ['/pipeline', 'Pipeline'], ['/messages', 'Messages'],
  ['/runs', 'Agent runs'], ['/analytics', 'Analytics'], ['/settings', 'Settings'],
] as const

export function Layout() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-full flex-col">
      <DegradedBanner />
      <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <button className="btn md:hidden" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
            <span className="text-lg font-bold tracking-tight text-brand">GigBid</span>
            <span className="hidden text-xs text-muted sm:inline">you approve every send</span>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-muted sm:inline">{user?.name} · {user?.account}</span>
            <button className="btn" onClick={signOut}>Sign out</button>
          </div>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-7xl flex-1 gap-6 px-4 py-5">
        <nav aria-label="Main" className={`${open ? 'block' : 'hidden'} fixed inset-x-0 top-14 z-10 border-b border-line bg-white p-3 md:static md:block md:w-48 md:border-0 md:bg-transparent md:p-0`}>
          <ul className="flex flex-col gap-1">
            {NAV.map(([to, label]) => (
              <li key={to}>
                <NavLink to={to} onClick={() => setOpen(false)}
                  className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-brand-soft font-semibold text-brand' : 'text-slate-700 hover:bg-white'}`}>
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="min-w-0 flex-1"><Outlet /></main>
      </div>
    </div>
  )
}
