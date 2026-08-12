import { Routes, Route, Navigate } from 'react-router-dom'
import { Component, type ReactNode } from 'react'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { RunProvider } from './contexts/RunContext'
import { ToastProvider } from './contexts/ToastContext'
import RequireRole from './components/layout/RequireRole'
import LoginPage from './pages/LoginPage'
import SignUpPage from './pages/SignUpPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import AuthPage from './pages/AuthPage'
import DashboardPage from './pages/DashboardPage'
import AnalysisPage from './pages/AnalysisPage'
import RunsHistoryPage from './pages/RunsHistoryPage'
import EndpointsPage from './pages/EndpointsPage'
import WorkflowsPage from './pages/WorkflowsPage'
import OpenAPIPage from './pages/OpenAPIPage'
import RagPage from './pages/RagPage'
import AutomationPage from './pages/AutomationPage'
import AutomationListPage from './pages/AutomationListPage'
import BulkPage from './pages/BulkPage'
import ApprovalsPage from './pages/ApprovalsPage'
import ReportsPage from './pages/ReportsPage'
import UsersPage from './pages/UsersPage'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null }
  static getDerivedStateFromError(e: Error) { return { error: e.message } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, fontFamily: 'monospace', background: '#fff8f8', minHeight: '100vh' }}>
          <h2 style={{ color: '#c00' }}>Render error</h2>
          <pre style={{ color: '#900', whiteSpace: 'pre-wrap' }}>{this.state.error}</pre>
          <button onClick={() => { this.setState({ error: null }); window.location.href = '/login' }}
            style={{ marginTop: 16, padding: '8px 16px', cursor: 'pointer' }}>
            Back to login
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

const ADMIN_OPERATOR = ['ADMIN', 'OPERATOR']
const ADMIN_ONLY     = ['ADMIN']

function AppRoutes() {
  return (
    <Routes>
      {/* ── Auth pages (follow the app's light/dark theme; each carries its own toggle) ── */}
      <Route path="/login"          element={<AuthPage />} />
      <Route path="/signup"         element={<SignUpPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password"  element={<ResetPasswordPage />} />
      <Route path="/auth"           element={<LoginPage />} />

      {/* ── Accessible to ALL roles ───────────────────────────────── */}
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/runs"      element={<RunsHistoryPage />} />
      <Route path="/endpoints" element={<EndpointsPage />} />
      <Route path="/reports"   element={<ReportsPage />} />

      {/* ── ADMIN + OPERATOR only ─────────────────────────────────── */}
      <Route path="/analysis"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><AnalysisPage /></RequireRole>} />
      <Route path="/workflows"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><WorkflowsPage /></RequireRole>} />
      <Route path="/openapi"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><OpenAPIPage /></RequireRole>} />
      <Route path="/rag"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><RagPage /></RequireRole>} />
      <Route path="/automation"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><AutomationPage /></RequireRole>} />
      <Route path="/automation-list"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><AutomationListPage /></RequireRole>} />
      <Route path="/bulk"
        element={<RequireRole allowedRoles={ADMIN_OPERATOR}><BulkPage /></RequireRole>} />

      {/* ── ADMIN only ────────────────────────────────────────────── */}
      <Route path="/approvals"
        element={<RequireRole allowedRoles={ADMIN_ONLY}><ApprovalsPage /></RequireRole>} />
      <Route path="/users"
        element={<RequireRole allowedRoles={ADMIN_ONLY}><UsersPage /></RequireRole>} />

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <RunProvider>
            <ToastProvider>
              <AppRoutes />
            </ToastProvider>
          </RunProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App
