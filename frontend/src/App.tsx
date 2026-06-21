import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import LoginPage from './pages/LoginPage'
import SignUpPage from './pages/SignUpPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import AuthPage from './pages/AuthPage'
import DashboardPage from './pages/DashboardPage'
import AnalysisPage from './pages/AnalysisPage'
import EndpointsPage from './pages/EndpointsPage'
import WorkflowsPage from './pages/WorkflowsPage'
import OpenAPIPage from './pages/OpenAPIPage'
import RagPage from './pages/RagPage'
import AutomationPage from './pages/AutomationPage'
import BulkPage from './pages/BulkPage'
import ApprovalsPage from './pages/ApprovalsPage'
import ReportsPage from './pages/ReportsPage'
import SettingsPage from './pages/SettingsPage'
import UsersPage from './pages/UsersPage'

function AppRoutes() {
  return (
    <Routes>
      {/* Auth pages */}
      <Route path="/login" element={<AuthPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/auth" element={<LoginPage />} />
      {/* App pages — redirect to /login if not authenticated (handled in AppLayout) */}
      <Route path="/dashboard"  element={<DashboardPage />} />
      <Route path="/analysis"   element={<AnalysisPage />} />
      <Route path="/endpoints"  element={<EndpointsPage />} />
      <Route path="/workflows"  element={<WorkflowsPage />} />
      <Route path="/openapi"    element={<OpenAPIPage />} />
      <Route path="/rag"        element={<RagPage />} />
      <Route path="/automation" element={<AutomationPage />} />
      <Route path="/bulk"       element={<BulkPage />} />
      <Route path="/approvals"  element={<ApprovalsPage />} />
      <Route path="/reports"    element={<ReportsPage />} />
      <Route path="/settings"   element={<SettingsPage />} />
      <Route path="/users"      element={<UsersPage />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
