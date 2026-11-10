import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { AuthProvider, useAuth } from './lib/auth'

const Login = lazy(() => import('./app/login/page'))
const Inbox = lazy(() => import('./app/inbox/page'))
const JobDetail = lazy(() => import('./app/jobs/[id]/page'))
const Studio = lazy(() => import('./app/studio/[id]/page'))
const Approvals = lazy(() => import('./app/approvals/page'))
const Pipeline = lazy(() => import('./app/pipeline/page'))
const Messages = lazy(() => import('./app/messages/page'))
const Runs = lazy(() => import('./app/runs/page'))
const Run = lazy(() => import('./app/runs/[id]/page'))
const Analytics = lazy(() => import('./app/analytics/page'))
const Settings = lazy(() => import('./app/settings/page'))

function Private({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Private><Layout /></Private>}>
              <Route path="/" element={<Navigate to="/inbox" replace />} />
              <Route path="/inbox" element={<Inbox />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/studio/:id" element={<Studio />} />
              <Route path="/approvals" element={<Approvals />} />
              <Route path="/pipeline" element={<Pipeline />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<Run />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/inbox" replace />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  )
}
