import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ArrowLeft, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { useTheme } from '../contexts/ThemeContext'
import ThemeToggleButton from '../components/ThemeToggleButton'

const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const { theme } = useTheme()
  const isLight = theme === 'light'

  // Only the page background follows the theme — the card itself always
  // renders in its light appearance (same decision as AuthPage's form panel).
  const t = {
    pageBg:     isLight ? '#f8faff' : '#0d0f1b',
    cardBg:     '#ffffff',
    cardBorder: '#e2e8f0',
    cardShadow: '0 8px 32px rgba(15,23,42,0.08)',
    heading:    '#0f172a',
    body:       '#64748b',
    subtitle:   '#64748b',
    hint:       '#94a3b8',
    footer:     isLight ? '#94a3b8' : 'rgba(255,255,255,0.2)',
    accent:     '#dc2626',
    inputBg:    '#ffffff',
    inputText:  'text-[#0f172a]',
    inputPh:    'placeholder-[#94a3b8]',
    inputBorder:'#e2e8f0',
    orbOpacity1:isLight ? 0.1 : 0.18,
    orbOpacity2:isLight ? 0.08 : 0.15,
    gridOpacity:isLight ? 0.035 : 0.07,
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    setLoading(true)
    try {
      await api.post('/auth/forgot-password', { email })
    } catch {
      // Always show success to prevent user enumeration
    } finally {
      setLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden" style={{ background: t.pageBg }}>
      <ThemeToggleButton />
      <div className="absolute top-[-8%] right-[-4%] w-[480px] h-[480px] rounded-full animate-blob pointer-events-none" style={{ background: '#dc2626', opacity: t.orbOpacity1, filter: 'blur(90px)' }} />
      <div className="absolute bottom-[-10%] left-[-6%] w-[400px] h-[400px] rounded-full animate-blob-delay pointer-events-none" style={{ background: '#f97316', opacity: t.orbOpacity2, filter: 'blur(80px)' }} />
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle, rgba(220,38,38,0.5) 1px, transparent 1px)', backgroundSize: '28px 28px', opacity: t.gridOpacity }} />

      <div className="relative w-full max-w-md animate-fade-up">
        <div className="rounded-2xl px-8 py-9" style={{ background: t.cardBg, border: `1px solid ${t.cardBorder}`, boxShadow: t.cardShadow, colorScheme: 'light' }}>
          {submitted ? (
            /* État de succès */
            <div className="flex flex-col items-center text-center animate-fade-up">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
                <CheckCircle2 size={28} style={{ color: '#22c55e' }} />
              </div>
              <h2 className="text-lg font-semibold mb-2" style={{ color: t.heading }}>Check your inbox</h2>
              <p className="text-sm mb-1" style={{ color: t.body }}>We sent a reset link to</p>
              <p className="text-sm font-semibold mb-6" style={{ color: t.accent }}>{email}</p>
              <p className="text-xs mb-6" style={{ color: t.hint }}>Didn't receive it? Check your spam folder or try again in a few minutes.</p>
              <Link to="/" className="text-sm font-medium flex items-center gap-1.5 transition-colors" style={{ color: t.accent }}>
                <ArrowLeft size={14} />
                Back to login
              </Link>
            </div>
          ) : (
            /* Formulaire */
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold mb-1" style={{ color: t.heading }}>Reset your password</h2>
                <p className="text-sm" style={{ color: t.body }}>Enter your email and we'll send you a reset link.</p>
              </div>
              <form onSubmit={handleSubmit} noValidate>
                <div className="mb-6">
                  <label htmlFor="email" className="block text-sm font-medium mb-1.5" style={{ color: t.hint }}>Email address</label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: t.hint }} />
                    <input
                      id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com" autoComplete="email" required
                      className={`w-full pl-10 pr-4 py-2.5 rounded-xl text-sm ${t.inputText} ${t.inputPh} transition-all duration-150 force-light-autofill`}
                      style={{ background: t.inputBg, border: `1.5px solid ${t.inputBorder}`, outline: 'none' }}
                      onFocus={(e) => (e.currentTarget.style.borderColor = '#dc2626')}
                      onBlur={(e) => (e.currentTarget.style.borderColor = t.inputBorder)}
                    />
                  </div>
                </div>
                <button
                  type="submit" disabled={loading || !email}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                  style={{ background: 'linear-gradient(135deg, #dc2626, #f97316)', boxShadow: '0 4px 14px 0 rgba(220, 38, 38, 0.35)' }}
                  onMouseEnter={(e) => { if (!loading) e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)' }}
                >
                  {loading ? (
                    <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Sending…</>
                  ) : 'Send link'}
                </button>
              </form>
              <div className="text-center mt-6">
                <Link to="/" className="text-sm font-medium flex items-center justify-center gap-1.5 transition-colors" style={{ color: t.accent }}>
                  <ArrowLeft size={14} />
                  Back to login
                </Link>
              </div>
            </>
          )}
        </div>
        <p className="text-center text-xs mt-4" style={{ color: t.footer }}>© 2026 ARIA · Final Year Project</p>
      </div>
    </div>
  )
}

export default ForgotPasswordPage
