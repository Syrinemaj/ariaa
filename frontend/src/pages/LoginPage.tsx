import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Mail, Lock, Eye, EyeOff, ArrowRight,
  AlertCircle, Clock, Zap, Shield, BarChart2, CheckCircle2,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

// ─── ARIA Layered Hexagon Logo ───────────────────────────────────────────────
const ARIALogo: React.FC<{ size?: number; variant?: 'light' | 'color' }> = ({
  size = 36,
  variant = 'color',
}) => {
  const h = Math.round(size * 44 / 36)
  const gradId = `hg-${variant}`
  return (
    <svg width={size} height={h} viewBox="0 0 36 44" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="36" y2="44" gradientUnits="userSpaceOnUse">
          {variant === 'light' ? (
            <>
              <stop stopColor="#ffffff" />
              <stop offset="1" stopColor="#ffffff" stopOpacity="0.7" />
            </>
          ) : (
            <>
              <stop stopColor="#6366f1" />
              <stop offset="1" stopColor="#8b5cf6" />
            </>
          )}
        </linearGradient>
      </defs>
      {/* Outer hex – translucent halo */}
      <path
        d="M18 2L34 11V29L18 38L2 29V11Z"
        fill={`url(#${gradId})`}
        opacity="0.22"
      />
      {/* Inner hex – solid */}
      <path
        d="M18 7L30 14.5V27.5L18 35L6 27.5V14.5Z"
        fill={`url(#${gradId})`}
      />
    </svg>
  )
}

// ─── Alert Banner ────────────────────────────────────────────────────────────
type AlertVariant = 'error' | 'warning' | 'rejected'

const ALERT_STYLE: Record<AlertVariant, {
  bg: string; border: string; icon: string; text: string
}> = {
  error:    { bg: '#fef2f2', border: '#fecaca', icon: '#ef4444', text: '#b91c1c' },
  warning:  { bg: '#fffbeb', border: '#fde68a', icon: '#d97706', text: '#92400e' },
  rejected: { bg: '#fef2f2', border: '#fecaca', icon: '#ef4444', text: '#b91c1c' },
}

interface AlertBannerProps {
  variant: AlertVariant
  message: string
  reason?: string
}

const AlertBanner: React.FC<AlertBannerProps> = ({ variant, message, reason }) => {
  const s = ALERT_STYLE[variant]
  return (
    <div
      className="flex items-start gap-3 rounded-xl px-4 py-3.5 text-sm mb-5 animate-fade-in"
      style={{ backgroundColor: s.bg, border: `1px solid ${s.border}` }}
      role="alert"
      aria-live="polite"
    >
      {variant === 'warning'
        ? <Clock size={15} style={{ color: s.icon, marginTop: 1, flexShrink: 0 }} />
        : <AlertCircle size={15} style={{ color: s.icon, marginTop: 1, flexShrink: 0 }} />
      }
      <div>
        <p style={{ color: s.text }} className="font-semibold leading-snug">{message}</p>
        {reason && (
          <p style={{ color: s.text }} className="mt-0.5 text-xs opacity-75">{reason}</p>
        )}
      </div>
    </div>
  )
}

// ─── Left panel data ─────────────────────────────────────────────────────────
const FEATURES = [
  { icon: Zap,      label: 'Découverte API',  sub: '247 endpoints cartographiés'   },
  { icon: Shield,   label: 'Audit Sécurité', sub: 'Couverture OWASP Top 10'  },
  { icon: BarChart2,label: 'Moniteur Live',   sub: '99,2% de disponibilité suivie'   },
]

const API_LOG = [
  { method: 'GET',    path: '/api/v2/users',          status: 200, ms: '142ms', ok: true  },
  { method: 'POST',   path: '/api/v2/auth/token',     status: 201, ms:  '89ms', ok: true  },
  { method: 'GET',    path: '/api/v2/endpoints',      status: 200, ms: '234ms', ok: true  },
  { method: 'DELETE', path: '/api/v2/sessions/9f2a',  status: 403, ms:  '44ms', ok: false },
]

const METHOD_COLOR: Record<string, string> = {
  GET:    '#818cf8',
  POST:   '#34d399',
  DELETE: '#f87171',
  PUT:    '#fbbf24',
  PATCH:  '#a78bfa',
}

// ─── Page ────────────────────────────────────────────────────────────────────
const LoginPage: React.FC = () => {
  const navigate   = useNavigate()
  const { login }  = useAuth()

  const [email,        setEmail]        = useState('')
  const [password,     setPassword]     = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember,     setRemember]     = useState(false)
  const [loading,      setLoading]      = useState(false)
  const [alert, setAlert] = useState<{
    variant: AlertVariant; message: string; reason?: string
  } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) return
    setLoading(true)
    setAlert(null)

    const result = await login(email, password)
    setLoading(false)

    if (result.success) {
      navigate('/dashboard')
    } else if (result.status === 'pending') {
      setAlert({ variant: 'warning', message: 'Votre compte est en attente d\'approbation par un manager.' })
    } else if (result.status === 'rejected') {
      setAlert({ variant: 'rejected', message: 'Votre compte a été rejeté.', reason: result.reason })
    } else {
      setAlert({ variant: 'error', message: result.error ?? 'Email ou mot de passe invalide.' })
    }
  }

  // Shared input handlers
  const iStyle: React.CSSProperties = { border: '1.5px solid rgba(255,255,255,0.1)', outline: 'none' }
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) =>
    (e.currentTarget.style.borderColor = '#6366f1')
  const onBlur  = (e: React.FocusEvent<HTMLInputElement>) =>
    (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')

  return (
    <div className="min-h-[100dvh] flex flex-col lg:flex-row overflow-hidden">

      {/* ════════════════════════════════════════════════════════════
          LEFT  —  brand / showcase panel
      ════════════════════════════════════════════════════════════ */}
      <div
        className="hidden lg:flex flex-col lg:w-[52%] relative overflow-hidden"
        style={{ background: 'linear-gradient(145deg, #0f0a2e 0%, #1e1b4b 38%, #2d1b69 72%, #3b0f6b 100%)' }}
      >
        {/* Dot grid */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.055) 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        />

        {/* Animated blobs */}
        <div
          className="absolute -top-[10%] -right-[12%] w-[560px] h-[560px] rounded-full pointer-events-none animate-blob"
          style={{ background: '#6366f1', opacity: 0.22, filter: 'blur(90px)' }}
        />
        <div
          className="absolute -bottom-[12%] -left-[10%] w-[420px] h-[420px] rounded-full pointer-events-none animate-blob-delay"
          style={{ background: '#8b5cf6', opacity: 0.2, filter: 'blur(75px)' }}
        />
        <div
          className="absolute top-[42%] right-[18%] w-[220px] h-[220px] rounded-full pointer-events-none"
          style={{ background: '#a78bfa', opacity: 0.1, filter: 'blur(45px)' }}
        />

        {/* Top accent shimmer line */}
        <div
          className="absolute top-0 left-0 right-0 h-px pointer-events-none"
          style={{ background: 'linear-gradient(90deg, transparent 0%, rgba(139,92,246,0.55) 50%, transparent 100%)' }}
        />

        {/* ── Content ── */}
        <div className="relative flex flex-col h-full px-12 py-11">

          {/* Logo */}
          <div className="flex items-center gap-2.5 mb-auto pb-10">
            <ARIALogo size={28} variant="light" />
            <span className="text-lg font-bold text-white tracking-tight">aria</span>
          </div>

          {/* Center block */}
          <div className="flex-1 flex flex-col justify-center">

            {/* Category badge */}
            <div
              className="inline-flex items-center gap-2 self-start px-3 py-1 rounded-full text-xs font-semibold mb-6"
              style={{
                background: 'rgba(99,102,241,0.22)',
                border:     '1px solid rgba(139,92,246,0.4)',
                color:      '#c4b5fd',
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#a78bfa] animate-pulse" />
              API Intelligence Platform
            </div>

            {/* Headline */}
            <h1 className="text-[2.6rem] font-extrabold text-white leading-[1.15] tracking-tight mb-4">
              Rétro-ingénierie<br />de toute API instantanément.
            </h1>
            <p className="text-sm text-white/55 leading-relaxed max-w-[44ch] mb-10">
              Capturez le trafic HTTP, cartographiez chaque endpoint, détectez les vulnérabilités
              et générez automatiquement la documentation — tout en un seul outil.
            </p>

            {/* Feature pills */}
            <div className="flex flex-wrap gap-3 mb-10">
              {FEATURES.map(({ icon: Icon, label, sub }) => (
                <div
                  key={label}
                  className="flex items-center gap-3 px-4 py-2.5 rounded-xl transition-colors duration-200"
                  style={{
                    background: 'rgba(255,255,255,0.06)',
                    border:     '1px solid rgba(255,255,255,0.1)',
                  }}
                >
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(99,102,241,0.35)' }}
                  >
                    <Icon size={13} style={{ color: '#a78bfa' }} />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-white leading-none mb-0.5">{label}</p>
                    <p className="text-[11px] text-white/40">{sub}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Terminal card */}
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background:    'rgba(0,0,0,0.38)',
                border:        '1px solid rgba(255,255,255,0.1)',
                backdropFilter:'blur(14px)',
              }}
            >
              {/* Title bar */}
              <div
                className="flex items-center justify-between px-4 py-3"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}
              >
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#ff5f57' }} />
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#febc2e' }} />
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#28c840' }} />
                </div>
                <span className="font-mono text-[11px] text-white/28">aria · live capture</span>
                <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#4ade80]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
                  En direct
                </div>
              </div>

              {/* Log rows */}
              <div className="px-4 py-3 space-y-2.5">
                {API_LOG.map((row, i) => (
                  <div key={i} className="flex items-center gap-3 text-[12px] font-mono">
                    <span
                      className="font-bold w-14 flex-shrink-0 text-right"
                      style={{ color: METHOD_COLOR[row.method] ?? '#94a3b8' }}
                    >
                      {row.method}
                    </span>
                    <span className="flex-1 text-white/50 truncate">{row.path}</span>
                    <span
                      className="font-semibold flex-shrink-0 w-8 text-center"
                      style={{ color: row.ok ? '#4ade80' : '#fb923c' }}
                    >
                      {row.status}
                    </span>
                    <span className="text-white/28 flex-shrink-0 w-11 text-right">{row.ms}</span>
                  </div>
                ))}
              </div>

              {/* Stats footer */}
              <div
                className="flex items-center gap-5 px-4 py-3"
                style={{
                  borderTop: '1px solid rgba(255,255,255,0.07)',
                  background: 'rgba(0,0,0,0.22)',
                }}
              >
                {[
                  { val: '247',   lbl: 'endpoints'      },
                  { val: '3',     lbl: 'vulnérabilités' },
                  { val: '99,2%', lbl: 'disponibilité'  },
                ].map(({ val, lbl }) => (
                  <div key={lbl} className="flex items-center gap-1.5">
                    <CheckCircle2 size={11} style={{ color: '#22c55e', flexShrink: 0 }} />
                    <span className="font-mono text-[11px] text-white/65 font-semibold">{val}</span>
                    <span className="font-mono text-[11px] text-white/28">{lbl}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Footer */}
          <p className="text-[11px] text-white/18 mt-10">© 2026 ARIA · PFE</p>
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════
          RIGHT  —  form panel
      ════════════════════════════════════════════════════════════ */}
      <div className="flex-1 flex items-center justify-center min-h-[100dvh] lg:min-h-0 px-6 sm:px-12 py-10 bg-[#0d0f1b] relative overflow-hidden">

        {/* Background blobs */}
        <div
          className="absolute -top-[8%] -right-[6%] w-[420px] h-[420px] rounded-full pointer-events-none animate-blob"
          style={{ background: '#6366f1', opacity: 0.15, filter: 'blur(80px)' }}
        />
        <div
          className="absolute -bottom-[8%] -left-[5%] w-[320px] h-[320px] rounded-full pointer-events-none animate-blob-delay"
          style={{ background: '#8b5cf6', opacity: 0.12, filter: 'blur(70px)' }}
        />

        {/* Dot grid */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.5) 1px, transparent 1px)',
            backgroundSize:  '28px 28px',
            opacity:          0.07,
          }}
        />

        {/* ── Form card ── */}
        <div className="relative w-full max-w-sm animate-fade-up">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-9">
            <ARIALogo size={26} variant="color" />
            <span
              className="text-xl font-bold tracking-tight"
              style={{
                background:           'linear-gradient(135deg, #6366f1, #8b5cf6)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor:  'transparent',
                backgroundClip:       'text',
              }}
            >
              aria
            </span>
          </div>

          {/* Heading block */}
          <div className="mb-7">
            <h2 className="text-[1.65rem] font-bold tracking-tight leading-tight mb-1.5" style={{ color: '#e2e8f0' }}>
              Bienvenue
            </h2>
            <p className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>
              Connectez-vous à votre espace ARIA pour continuer.
            </p>
          </div>

          {/* Alert */}
          {alert && (
            <AlertBanner
              variant={alert.variant}
              message={alert.message}
              reason={alert.reason}
            />
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} noValidate className="space-y-4">

            {/* Email */}
            <div>
              <label htmlFor="login-email" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>
                Adresse email
              </label>
              <div className="relative">
                <Mail
                  size={15}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] pointer-events-none"
                />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="vous@exemple.com"
                  autoComplete="email"
                  required
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm text-white placeholder-[rgba(255,255,255,0.3)] bg-[#1a1d2e] transition-all duration-150"
                  style={iStyle}
                  onFocus={onFocus}
                  onBlur={onBlur}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="login-password" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>
                Mot de passe
              </label>
              <div className="relative">
                <Lock
                  size={15}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] pointer-events-none"
                />
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  className="w-full pl-10 pr-10 py-2.5 rounded-xl text-sm text-[#0f172a] placeholder-[#94a3b8] bg-white transition-all duration-150"
                  style={iStyle}
                  onFocus={onFocus}
                  onBlur={onBlur}
                />
                <button
                  type="button"
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] hover:text-[#64748b] transition-colors cursor-pointer"
                  onClick={() => setShowPassword((p) => !p)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Remember me + Forgot password */}
            <div className="flex items-center justify-between pt-0.5">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#6366f1] cursor-pointer"
                />
                <span className="text-sm text-[#64748b]">Se souvenir de moi</span>
              </label>
              <Link
                to="/forgot-password"
                className="text-sm font-semibold text-[#6366f1] hover:text-[#4f46e5] transition-colors"
              >
                Mot de passe oublié ?
              </Link>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !email || !password}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
              style={{
                background:  'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                boxShadow:   '0 4px 16px 0 rgba(99, 102, 241, 0.38)',
                marginTop:   '4px',
              }}
              onMouseEnter={(e) => {
                if (!loading) e.currentTarget.style.transform = 'translateY(-2px)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)'
              }}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Connexion en cours…
                </>
              ) : (
                <>
                  Se connecter
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-[#e2e8f0]" />
            <span className="text-xs text-[#94a3b8] font-medium">Nouveau sur ARIA ?</span>
            <div className="flex-1 h-px bg-[#e2e8f0]" />
          </div>

          {/* Demander l'accès */}
          <Link
            to="/signup"
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-semibold text-[#6366f1] bg-white transition-all duration-200 cursor-pointer hover:-translate-y-0.5"
            style={{ border: '1.5px solid #e2e8f0', boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.04)' }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#c7d2fe')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#e2e8f0')}
          >
            Demander l'accès
          </Link>

          {/* Pied de page mobile */}
          <p className="lg:hidden text-center text-xs text-[#94a3b8] mt-8">
            © 2026 ARIA · PFE
          </p>
        </div>
      </div>

    </div>
  )
}

export default LoginPage
