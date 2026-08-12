import React, { useState, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { Lock, Eye, EyeOff, CheckCircle2, AlertCircle, ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'
import { useTheme } from '../contexts/ThemeContext'
import ThemeToggleButton from '../components/ThemeToggleButton'

const ResetPasswordPage: React.FC = () => {
  const [searchParams]                  = useSearchParams()
  const navigate                        = useNavigate()
  const token                           = searchParams.get('token') ?? ''

  const [password, setPassword]         = useState('')
  const [confirm, setConfirm]           = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm]   = useState(false)
  const [loading, setLoading]           = useState(false)
  const [success, setSuccess]           = useState(false)
  const [error, setError]               = useState('')
  const { theme }                       = useTheme()
  const isLight                         = theme === 'light'

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
    trackEmpty: '#e2e8f0',
    errBg:      '#fef2f2',
    errBorder:  '#fecaca',
    errText:    '#b91c1c',
    orbOpacity1:isLight ? 0.1 : 0.18,
    orbOpacity2:isLight ? 0.08 : 0.15,
    gridOpacity:isLight ? 0.035 : 0.07,
  }

  // Rediriger vers /forgot-password si pas de token
  useEffect(() => {
    if (!token) navigate('/forgot-password', { replace: true })
  }, [token, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      setSuccess(true)
      setTimeout(() => navigate('/login', { replace: true }), 3000)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('400')) {
        setError('This reset link is invalid or has expired. Please request a new one.')
      } else {
        setError('An error occurred. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const inputBase = `w-full pl-10 pr-10 py-2.5 rounded-xl text-sm ${t.inputText} ${t.inputPh} transition-all duration-150 force-light-autofill`
  const inputStyle = { background: t.inputBg, border: `1.5px solid ${t.inputBorder}`, outline: 'none' }
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = '#dc2626')
  const onBlur  = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = t.inputBorder)

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden" style={{ background: t.pageBg }}>
      <ThemeToggleButton />
      <div className="absolute top-[-8%] right-[-4%] w-[480px] h-[480px] rounded-full animate-blob pointer-events-none" style={{ background: '#dc2626', opacity: t.orbOpacity1, filter: 'blur(90px)' }} />
      <div className="absolute bottom-[-10%] left-[-6%] w-[400px] h-[400px] rounded-full animate-blob-delay pointer-events-none" style={{ background: '#f97316', opacity: t.orbOpacity2, filter: 'blur(80px)' }} />
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle, rgba(220,38,38,0.5) 1px, transparent 1px)', backgroundSize: '28px 28px', opacity: t.gridOpacity }} />

      <div className="relative w-full max-w-md animate-fade-up">
        <div className="rounded-2xl px-8 py-9" style={{ background: t.cardBg, border: `1px solid ${t.cardBorder}`, boxShadow: t.cardShadow, colorScheme: 'light' }}>
          {success ? (
            <div className="flex flex-col items-center text-center animate-fade-up">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
                <CheckCircle2 size={28} style={{ color: '#22c55e' }} />
              </div>
              <h2 className="text-lg font-semibold mb-2" style={{ color: t.heading }}>Password changed!</h2>
              <p className="text-sm mb-6" style={{ color: t.body }}>
                Your password has been successfully updated.<br />
                You will be redirected to login…
              </p>
              <Link to="/login" className="text-sm font-medium flex items-center gap-1.5 transition-colors" style={{ color: t.accent }}>
                <ArrowLeft size={14} />
                Go to login
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold mb-1" style={{ color: t.heading }}>New password</h2>
                <p className="text-sm" style={{ color: t.body }}>
                  Choose a new, secure password.
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-2.5 rounded-xl px-4 py-3 mb-5" style={{ background: t.errBg, border: `1px solid ${t.errBorder}` }}>
                  <AlertCircle size={15} style={{ color: t.errText, marginTop: 1, flexShrink: 0 }} />
                  <p className="text-xs leading-relaxed" style={{ color: t.errText }}>{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {/* Nouveau mot de passe */}
                <div>
                  <label htmlFor="rp-password" className="block text-sm font-medium mb-1.5" style={{ color: t.hint }}>
                    New password
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: t.hint }} />
                    <input
                      id="rp-password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="Min. 8 characters"
                      autoComplete="new-password"
                      className={inputBase}
                      style={inputStyle}
                      onFocus={onFocus}
                      onBlur={onBlur}
                    />
                    <button
                      type="button"
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 cursor-pointer transition-colors"
                      style={{ color: t.hint }}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  {/* Force indicator */}
                  {password.length > 0 && (
                    <div className="mt-2 flex gap-1">
                      {[8, 12, 16].map((threshold, i) => (
                        <div
                          key={i}
                          className="h-1 flex-1 rounded-full transition-colors"
                          style={{
                            background: password.length >= threshold
                              ? i === 0 ? '#f59e0b' : i === 1 ? '#22c55e' : '#dc2626'
                              : t.trackEmpty,
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {/* Confirmer */}
                <div>
                  <label htmlFor="rp-confirm" className="block text-sm font-medium mb-1.5" style={{ color: t.hint }}>
                    Confirm password
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: t.hint }} />
                    <input
                      id="rp-confirm"
                      type={showConfirm ? 'text' : 'password'}
                      value={confirm}
                      onChange={e => setConfirm(e.target.value)}
                      placeholder="Repeat password"
                      autoComplete="new-password"
                      className={inputBase}
                      style={inputStyle}
                      onFocus={onFocus}
                      onBlur={onBlur}
                    />
                    <button
                      type="button"
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 cursor-pointer transition-colors"
                      style={{ color: t.hint }}
                      onClick={() => setShowConfirm(!showConfirm)}
                    >
                      {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading || !password || !confirm}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed mt-2"
                  style={{ background: 'linear-gradient(135deg, #dc2626, #f97316)', boxShadow: '0 4px 14px 0 rgba(220, 38, 38, 0.35)' }}
                  onMouseEnter={e => { if (!loading) e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)' }}
                >
                  {loading ? (
                    <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Updating…</>
                  ) : 'Change password'}
                </button>
              </form>

              <div className="text-center mt-6">
                <Link to="/forgot-password" className="text-sm font-medium flex items-center justify-center gap-1.5 transition-colors" style={{ color: t.accent }}>
                  <ArrowLeft size={14} />
                  Resend link
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

export default ResetPasswordPage
