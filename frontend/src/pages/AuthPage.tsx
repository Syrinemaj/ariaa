import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    Mail, Lock, Eye, EyeOff, ArrowRight, User,
    AlertCircle, Clock, CheckCircle2, Info,
    Zap, Shield, BarChart2, Activity, Cpu, GitBranch,
    Sun, Moon,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'
import { api, ApiError } from '../lib/api'


// ─── Animated counter ─────────────────────────────────────────────────────────
const Counter: React.FC<{ to: number; suffix?: string; duration?: number }> = ({ to, suffix = '', duration = 1800 }) => {
    const [val, setVal] = useState(0)
    useEffect(() => {
        let start = 0
        const step = Math.ceil(to / (duration / 16))
        const t = setInterval(() => {
            start += step
            if (start >= to) { setVal(to); clearInterval(t) }
            else setVal(start)
        }, 16)
        return () => clearInterval(t)
    }, [to])
    return <>{val.toLocaleString()}{suffix}</>
}

// ─── Live log rows ─────────────────────────────────────────────────────────────
const LOGS = [
    { method: 'GET', path: '/api/v2/users/profile', status: 200, ms: 142, ok: true },
    { method: 'POST', path: '/api/v2/auth/token', status: 201, ms: 89, ok: true },
    { method: 'GET', path: '/api/v2/sessions/list', status: 200, ms: 234, ok: true },
    { method: 'DELETE', path: '/api/v2/sessions/9f2a', status: 403, ms: 44, ok: false },
    { method: 'PATCH', path: '/api/v2/users/settings', status: 200, ms: 178, ok: true },
    { method: 'POST', path: '/api/v2/endpoints/enrich', status: 202, ms: 512, ok: true },
]
const MC_DARK: Record<string, string> = {
    GET: '#fb923c', POST: '#34d399', DELETE: '#f87171', PATCH: '#fbbf24', PUT: '#fdba74',
}
const MC_LIGHT: Record<string, string> = {
    GET: '#ea580c', POST: '#059669', DELETE: '#dc2626', PATCH: '#d97706', PUT: '#c2410c',
}

type Mode = 'login' | 'register'

export default function AuthPage() {
    const navigate = useNavigate()
    const { login } = useAuth()
    const { theme, toggleTheme } = useTheme()
    const [mode, setMode] = useState<Mode>('login')
    const [visibleLogs, setVisibleLogs] = useState(LOGS.slice(0, 4))

    // Only the left "pub" marketing panel follows the app theme — the
    // Welcome/Request access form panel stays light in both modes.
    const isDarkPub = theme === 'dark'
    const MC = isDarkPub ? MC_DARK : MC_LIGHT
    const pub = {
        bg:                 isDarkPub ? '#070b1a' : '#fff7f4',
        gridLine:           isDarkPub ? 'rgba(220,38,38,0.07)' : 'rgba(220,38,38,0.06)',
        orb1:               isDarkPub ? 'rgba(220,38,38,0.35)' : 'rgba(220,38,38,0.14)',
        orb2:               isDarkPub ? 'rgba(249,115,22,0.28)' : 'rgba(249,115,22,0.14)',
        orb3:               isDarkPub ? 'rgba(234,88,12,0.15)' : 'rgba(234,88,12,0.10)',
        scanLine:           isDarkPub ? 'rgba(220,38,38,0.5)' : 'rgba(220,38,38,0.25)',
        topShimmer:         isDarkPub ? 'rgba(249,115,22,0.8)' : 'rgba(249,115,22,0.4)',
        toggleBg:           isDarkPub ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.04)',
        toggleBorder:       isDarkPub ? 'rgba(255,255,255,0.14)' : 'rgba(15,23,42,0.1)',
        versionBg:          isDarkPub ? 'rgba(220,38,38,0.15)' : 'rgba(220,38,38,0.08)',
        versionBorder:      isDarkPub ? 'rgba(220,38,38,0.3)' : 'rgba(220,38,38,0.25)',
        versionText:        isDarkPub ? '#fca5a5' : '#dc2626',
        eyebrowBg:          isDarkPub ? 'rgba(220,38,38,0.12)' : 'rgba(220,38,38,0.08)',
        eyebrowBorder:      isDarkPub ? 'rgba(249,115,22,0.35)' : 'rgba(249,115,22,0.3)',
        eyebrowText:        isDarkPub ? '#fdba74' : '#c2410c',
        headline:           isDarkPub ? '#ffffff' : '#0f172a',
        body:               isDarkPub ? 'rgba(255,255,255,0.45)' : '#64748b',
        statCardBg:         isDarkPub ? 'rgba(255,255,255,0.04)' : '#ffffff',
        statCardBorder:     isDarkPub ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)',
        statValue:          isDarkPub ? '#ffffff' : '#0f172a',
        statLabel:          isDarkPub ? 'rgba(255,255,255,0.35)' : '#94a3b8',
        terminalBg:         isDarkPub ? 'rgba(0,0,0,0.5)' : '#ffffff',
        terminalBorder:     isDarkPub ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.08)',
        terminalHeaderBg:   isDarkPub ? 'rgba(255,255,255,0.02)' : 'rgba(15,23,42,0.015)',
        terminalHeaderBorder: isDarkPub ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.06)',
        terminalTitle:      isDarkPub ? 'rgba(255,255,255,0.3)' : '#94a3b8',
        recordingBg:        isDarkPub ? 'rgba(34,197,94,0.12)' : 'rgba(34,197,94,0.1)',
        recordingBorder:    isDarkPub ? 'rgba(34,197,94,0.25)' : 'rgba(34,197,94,0.3)',
        recordingText:      isDarkPub ? '#4ade80' : '#16a34a',
        colHeaderText:      isDarkPub ? 'rgba(255,255,255,0.2)' : '#cbd5e1',
        colHeaderBorder:    isDarkPub ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.04)',
        colHeaderBg:        isDarkPub ? 'rgba(0,0,0,0.2)' : 'rgba(15,23,42,0.015)',
        rowHighlightBg:     isDarkPub ? 'rgba(220,38,38,0.08)' : 'rgba(220,38,38,0.06)',
        rowHighlightBorder: isDarkPub ? 'rgba(220,38,38,0.15)' : 'rgba(220,38,38,0.15)',
        pathText:           isDarkPub ? 'rgba(255,255,255,0.45)' : '#475569',
        latencyText:        isDarkPub ? 'rgba(255,255,255,0.25)' : '#94a3b8',
        footerTop:          isDarkPub ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.06)',
        footerBg:           isDarkPub ? 'rgba(0,0,0,0.3)' : 'rgba(15,23,42,0.015)',
        footerLabel:        isDarkPub ? 'rgba(255,255,255,0.3)' : '#94a3b8',
        footerValue:        isDarkPub ? 'rgba(255,255,255,0.6)' : '#334155',
        poweredText:        isDarkPub ? 'rgba(255,255,255,0.2)' : '#cbd5e1',
        copyrightText:      isDarkPub ? 'rgba(255,255,255,0.15)' : '#94a3b8',
        bottomBadgeBg:      isDarkPub ? 'rgba(220,38,38,0.1)' : 'rgba(220,38,38,0.06)',
        bottomBadgeBorder:  isDarkPub ? 'rgba(220,38,38,0.2)' : 'rgba(220,38,38,0.15)',
        bottomBadgeText:    isDarkPub ? 'rgba(252,165,165,0.6)' : '#dc2626',
    }

    // Simulate live log feed
    useEffect(() => {
        let idx = 4
        const t = setInterval(() => {
            setVisibleLogs(prev => {
                const next = [...prev.slice(1), LOGS[idx % LOGS.length]]
                idx++
                return next
            })
        }, 2200)
        return () => clearInterval(t)
    }, [])

    // Login
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPwd, setShowPwd] = useState(false)
    const [remember, setRemember] = useState(false)
    const [lLoading, setLLoading] = useState(false)
    const [lAlert, setLAlert] = useState<{ type: 'error' | 'warning'; msg: string } | null>(null)

    // Register
    const [rUser, setRUser] = useState('')
    const [rEmail, setREmail] = useState('')
    const [rPwd, setRPwd] = useState('')
    const [rConfirm, setRConfirm] = useState('')
    const [showRP, setShowRP] = useState(false)
    const [showRC, setShowRC] = useState(false)
    const [rLoading, setRLoading] = useState(false)
    const [rErrors, setRErrors] = useState<Record<string, string>>({})
    const [rDone, setRDone] = useState(false)
    const [rErr, setRErr] = useState('')

    const iStyle: React.CSSProperties = { border: '1.5px solid #e2e8f0', outline: 'none' }
    const onFocus = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = '#dc2626')
    const onBlur = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = '#e2e8f0')
    const iCls = 'w-full pl-10 pr-4 py-2.5 rounded-xl text-sm text-[#0f172a] placeholder-[#94a3b8] bg-white transition-all duration-150 force-light-autofill'

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!email || !password) return
        setLLoading(true); setLAlert(null)
        const r = await login(email, password)
        setLLoading(false)
        if (r.success) navigate('/dashboard')
        else if (r.status === 'pending') setLAlert({ type: 'warning', msg: 'Account pending approval.' })
        else setLAlert({ type: 'error', msg: r.error ?? 'Invalid credentials.' })
    }

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault()
        const errs: Record<string, string> = {}
        if (rUser.trim().length < 2) errs.user = 'Min. 2 characters'
        if (!rEmail.includes('@')) errs.email = 'Invalid email'
        if (rPwd.length < 8) errs.pwd = 'Min. 8 characters'
        if (rPwd !== rConfirm) errs.confirm = "Passwords do not match"
        setRErrors(errs)
        if (Object.keys(errs).length) return
        setRLoading(true); setRErr('')
        try {
            await api.post('/auth/request-access', {
                email: rEmail.trim().toLowerCase(),
                password: rPwd,
                full_name: rUser.trim(),
            })
            setRDone(true)
        } catch (err: unknown) {
            if (err instanceof ApiError) {
                if (err.status === 422) setRErr('Please check the information entered.')
                else if (err.status === 429) setRErr('Too many attempts. Try again in 1 minute.')
                else setRErr('An error occurred. Please try again.')
            } else {
                setRErr('Network error. Check your connection.')
            }
        } finally {
            setRLoading(false)
        }
    }

    return (
        <div style={{ fontFamily: "'Plus Jakarta Sans',sans-serif" }}>
            <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

        .ar { position:relative; width:100vw; height:100dvh; overflow:hidden; background:#f8faff; }

        /* Forms fixed */
        .f-login    { position:absolute; top:0; bottom:0; left:50%; width:50%; display:flex; align-items:center; justify-content:center; z-index:1; }
        .f-register { position:absolute; top:0; bottom:0; left:0;   width:50%; display:flex; align-items:center; justify-content:center; z-index:1; }

        /* Force light autofill chrome — browsers otherwise paint saved-credential
           inputs with a dark background (from OS/page dark mode) via the
           -webkit-autofill inset box-shadow trick, ignoring the input's own
           bg-white class. This keeps the Welcome/Request access forms light
           in both themes, as intended. */
        .f-login input:-webkit-autofill,
        .f-login input:-webkit-autofill:hover,
        .f-login input:-webkit-autofill:focus,
        .f-register input:-webkit-autofill,
        .f-register input:-webkit-autofill:hover,
        .f-register input:-webkit-autofill:focus {
          -webkit-text-fill-color: #0f172a !important;
          -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
          box-shadow: 0 0 0 1000px #ffffff inset !important;
          caret-color: #0f172a;
          transition: background-color 9999s ease-in-out 0s;
        }

        /* PUB glides as curtain */
        .pub { position:absolute; top:0; bottom:0; width:50%; z-index:10; transition:left 0.72s cubic-bezier(0.76,0,0.24,1); }
        .pub.login    { left:0%;  }
        .pub.register { left:50%; }

        /* Form reveal */
        @keyframes revealR { from{opacity:0;transform:translateX(24px)} to{opacity:1;transform:translateX(0)} }
        @keyframes revealL { from{opacity:0;transform:translateX(-24px)} to{opacity:1;transform:translateX(0)} }
        .reveal-right { animation:revealR 0.48s 0.38s cubic-bezier(0.22,1,0.36,1) both; }
        .reveal-left  { animation:revealL 0.48s 0.38s cubic-bezier(0.22,1,0.36,1) both; }

        /* Log row animation */
        @keyframes logSlide { from{opacity:0;transform:translateY(-10px)} to{opacity:1;transform:translateY(0)} }
        .log-row { animation:logSlide 0.35s ease both; }

        /* Glowing orbs */
        @keyframes orb1 { 0%,100%{transform:translate(0,0) scale(1)} 50%{transform:translate(30px,-20px) scale(1.1)} }
        @keyframes orb2 { 0%,100%{transform:translate(0,0) scale(1)} 50%{transform:translate(-20px,25px) scale(0.9)} }
        @keyframes orb3 { 0%,100%{transform:translate(0,0) scale(1)} 33%{transform:translate(15px,10px) scale(1.05)} 66%{transform:translate(-10px,-15px) scale(0.95)} }
        .orb1 { animation:orb1 9s ease-in-out infinite; }
        .orb2 { animation:orb2 11s ease-in-out 2s infinite; }
        .orb3 { animation:orb3 7s ease-in-out 1s infinite; }

        /* Pulse dot */
        @keyframes pdot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(0.85)} }
        .pdot { animation:pdot 1.6s ease-in-out infinite; }

        /* Scan line */
        @keyframes scan { from{top:0%} to{top:100%} }
        .scan-line { animation:scan 3s linear infinite; }

        /* Badge glow */
        @keyframes badgeGlow { 0%,100%{box-shadow:0 0 0 0 rgba(220,38,38,0)} 50%{box-shadow:0 0 12px 3px rgba(220,38,38,0.35)} }
        .badge-glow { animation:badgeGlow 3s ease-in-out infinite; }

        /* Shimmer on card */
        @keyframes shimmer { from{transform:translateX(-100%)} to{transform:translateX(200%)} }
        .shimmer::after {
          content:'';
          position:absolute; inset:0;
          background:linear-gradient(90deg,transparent,rgba(255,255,255,0.04),transparent);
          animation:shimmer 3s ease-in-out infinite;
        }

        /* Number tick */
        @keyframes tick { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        .tick { animation:tick 0.3s ease both; }

        /* Grid scroll */
        @keyframes gridScroll { from{background-position:0 0} to{background-position:0 40px} }
        .grid-scroll { animation:gridScroll 4s linear infinite; }
      `}</style>

            <div className="ar">

                {/* Bg for forms */}
                <div className="absolute inset-0 z-0 pointer-events-none">
                    <div className="absolute -top-20 -left-20 w-96 h-96 rounded-full orb1" style={{ background: 'radial-gradient(circle,rgba(220,38,38,0.08),transparent 70%)' }} />
                    <div className="absolute -bottom-20 -right-20 w-80 h-80 rounded-full orb2" style={{ background: 'radial-gradient(circle,rgba(249,115,22,0.07),transparent 70%)' }} />
                    <div className="absolute inset-0 grid-scroll" style={{ backgroundImage: 'radial-gradient(circle,#dc2626 1px,transparent 1px)', backgroundSize: '28px 28px', opacity: 0.025 }} />
                </div>

                {/* ════ FORM LOGIN ══════════════════════════════════════════════ */}
                <div className="f-login" style={{ colorScheme: 'light' }}>
                    <div className={`w-full max-w-sm px-10 ${mode === 'login' ? 'reveal-right' : ''}`} key={`l-${mode}`}>

                        <div className="mb-8">
                            <h2 className="text-2xl font-extrabold tracking-tight mb-1.5" style={{ color: '#0f172a' }}>Welcome</h2>
                            <p className="text-sm" style={{ color: '#64748b' }}>Log in to access your workspace</p>
                        </div>

                        {lAlert && (
                            <div className="flex items-start gap-3 rounded-2xl px-4 py-3.5 mb-5"
                                style={{ backgroundColor: lAlert.type === 'warning' ? '#fffbeb' : '#fef2f2', border: `1px solid ${lAlert.type === 'warning' ? '#fde68a' : '#fecaca'}` }}>
                                {lAlert.type === 'warning' ? <Clock size={15} style={{ color: '#d97706', marginTop: 1, flexShrink: 0 }} /> : <AlertCircle size={15} style={{ color: '#ef4444', marginTop: 1, flexShrink: 0 }} />}
                                <p className="text-sm font-medium" style={{ color: lAlert.type === 'warning' ? '#92400e' : '#b91c1c' }}>{lAlert.msg}</p>
                            </div>
                        )}

                        <form onSubmit={handleLogin} noValidate className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>Email</label>
                                <div className="relative">
                                    <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#94a3b8' }} />
                                    <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" required className={iCls} style={iStyle} onFocus={onFocus} onBlur={onBlur} />
                                </div>
                            </div>
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <label className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#94a3b8' }}>Password</label>
                                    <button type="button" className="text-xs font-semibold hover:opacity-70 transition-opacity" style={{ color: '#dc2626' }} onClick={() => navigate('/forgot-password')}>Forgot?</button>
                                </div>
                                <div className="relative">
                                    <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#94a3b8' }} />
                                    <input type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" required className={`${iCls} pr-10`} style={iStyle} onFocus={onFocus} onBlur={onBlur} />
                                    <button type="button" className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors" style={{ color: '#94a3b8' }} onClick={() => setShowPwd(p => !p)}>
                                        {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                                    </button>
                                </div>
                            </div>
                            <label className="flex items-center gap-2.5 cursor-pointer pt-1">
                                <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} className="w-4 h-4 rounded accent-[#dc2626]" />
                                <span className="text-sm" style={{ color: '#64748b' }}>Remember me for 30 days</span>
                            </label>
                            <button
                                type="submit" disabled={lLoading || !email || !password}
                                className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold text-white transition-all duration-200 disabled:opacity-50 mt-2"
                                style={{ background: 'linear-gradient(135deg,#dc2626,#f97316)', boxShadow: '0 4px 20px rgba(220,38,38,0.4)' }}
                                onMouseEnter={e => { if (!lLoading) (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 8px 28px rgba(220,38,38,0.5)' }}
                                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 4px 20px rgba(220,38,38,0.4)' }}
                            >
                                {lLoading ? <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Signing in…</> : <>Log in <ArrowRight size={15} /></>}
                            </button>
                        </form>

                        <div className="flex items-center gap-3 my-6">
                            <div className="flex-1 h-px" style={{ background: '#e2e8f0' }} />
                            <span className="text-xs font-medium" style={{ color: '#94a3b8' }}>Don't have an account?</span>
                            <div className="flex-1 h-px" style={{ background: '#e2e8f0' }} />
                        </div>

                        <button
                            onClick={() => setMode('register')}
                            className="w-full py-3 rounded-2xl text-sm font-bold transition-all duration-200"
                            style={{ border: '2px solid #e2e8f0', color: '#dc2626', background: 'transparent' }}
                            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#dc2626'; (e.currentTarget as HTMLButtonElement).style.background = '#fef2f2' }}
                            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#e2e8f0'; (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
                        >
                            Request access →
                        </button>
                    </div>
                </div>

                {/* ════ FORM REGISTER ══════════════════════════════════════════ */}
                <div className="f-register" style={{ colorScheme: 'light' }}>
                    <div className={`w-full max-w-sm px-10 overflow-y-auto max-h-[100dvh] py-10 ${mode === 'register' ? 'reveal-left' : ''}`} key={`r-${rDone}`}>
                        {rDone ? (
                            <div className="text-center py-8">
                                <div className="w-16 h-16 rounded-3xl flex items-center justify-center mx-auto mb-6" style={{ background: 'linear-gradient(135deg,#f0fdf4,#dcfce7)', border: '2px solid #bbf7d0' }}>
                                    <CheckCircle2 size={28} style={{ color: '#16a34a' }} />
                                </div>
                                <h2 className="text-2xl font-extrabold text-[#0f172a] mb-2">You're on the list!</h2>
                                <p className="text-sm text-[#64748b] mb-6">A manager will review your request and assign you a role.</p>
                                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold mb-8 badge-glow"
                                    style={{ background: 'linear-gradient(135deg,#fffbeb,#fef3c7)', border: '1px solid #fde68a', color: '#92400e' }}>
                                    <span className="w-2 h-2 rounded-full bg-amber-400 pdot" />Pending approval
                                </div>
                                <div>
                                    <button onClick={() => setMode('login')} className="text-sm font-bold text-[#dc2626] hover:text-[#b91c1c] transition-colors">← Back to login</button>
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="mb-6">
                                    <h2 className="text-2xl font-extrabold tracking-tight mb-1.5" style={{ color: '#0f172a' }}>Request access</h2>
                                    <p className="text-sm" style={{ color: '#64748b' }}>Join ARIA — a manager will assign you a role</p>
                                </div>

                                <div className="flex items-start gap-3 rounded-2xl px-4 py-3 mb-5" style={{ background: 'linear-gradient(135deg,#f0f9ff,#e0f2fe)', border: '1px solid #bae6fd' }}>
                                    <Info size={14} style={{ color: '#0284c7', marginTop: 2, flexShrink: 0 }} />
                                    <p className="text-xs leading-relaxed font-medium" style={{ color: '#0c4a6e' }}>Your account will be reviewed before activation. Your role will be assigned by your manager.</p>
                                </div>

                                {rErr && (
                                    <div className="flex items-center gap-2 rounded-2xl px-4 py-3 mb-4" style={{ background: '#fef2f2', border: '1px solid #fecaca' }}>
                                        <AlertCircle size={14} style={{ color: '#ef4444', flexShrink: 0 }} />
                                        <p className="text-xs font-medium" style={{ color: '#b91c1c' }}>{rErr}</p>
                                    </div>
                                )}

                                <form onSubmit={handleRegister} noValidate className="space-y-4">
                                    {[
                                        { label: "Username", id: 'user', type: 'text', val: rUser, set: setRUser, err: rErrors.user, icon: User, ph: 'your_username', ac: 'username' },
                                        { label: 'Email', id: 'email', type: 'email', val: rEmail, set: setREmail, err: rErrors.email, icon: Mail, ph: 'you@example.com', ac: 'email' },
                                    ].map(({ label, id, type, val, set, err, icon: Icon, ph, ac }) => (
                                        <div key={id}>
                                            <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>{label}</label>
                                            <div className="relative">
                                                <Icon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#94a3b8' }} />
                                                <input type={type} value={val} onChange={e => set(e.target.value)} placeholder={ph} autoComplete={ac} className={iCls} style={iStyle} onFocus={onFocus} onBlur={onBlur} />
                                            </div>
                                            {err && <p className="text-xs font-medium mt-1" style={{ color: '#ef4444' }}>{err}</p>}
                                        </div>
                                    ))}

                                    {/* Password */}
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>Password</label>
                                        <div className="relative">
                                            <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#94a3b8' }} />
                                            <input type={showRP ? 'text' : 'password'} value={rPwd} onChange={e => setRPwd(e.target.value)} placeholder="Min. 8 characters" autoComplete="new-password" className={`${iCls} pr-10`} style={iStyle} onFocus={onFocus} onBlur={onBlur} />
                                            <button type="button" style={{ color: '#94a3b8' }} className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors" onClick={() => setShowRP(p => !p)}>{showRP ? <EyeOff size={15} /> : <Eye size={15} />}</button>
                                        </div>
                                        {rErrors.pwd && <p className="text-xs font-medium mt-1" style={{ color: '#ef4444' }}>{rErrors.pwd}</p>}
                                        {rPwd && (
                                            <div className="flex gap-1 mt-2">
                                                {[rPwd.length >= 8, /[A-Z]/.test(rPwd), /[0-9]/.test(rPwd), /[^A-Za-z0-9]/.test(rPwd)].map((ok, i) => (
                                                    <div key={i} className="h-1 flex-1 rounded-full transition-all duration-300" style={{ background: ok ? (i < 2 ? '#f59e0b' : '#22c55e') : '#e2e8f0' }} />
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    {/* Confirmation */}
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>Confirm password</label>
                                        <div className="relative">
                                            <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#94a3b8' }} />
                                            <input type={showRC ? 'text' : 'password'} value={rConfirm} onChange={e => setRConfirm(e.target.value)} placeholder="Repeat password" autoComplete="new-password" className={`${iCls} pr-10`} style={iStyle} onFocus={onFocus} onBlur={onBlur} />
                                            <button type="button" style={{ color: '#94a3b8' }} className="absolute right-3.5 top-1/2 -translate-y-1/2 transition-colors" onClick={() => setShowRC(p => !p)}>{showRC ? <EyeOff size={15} /> : <Eye size={15} />}</button>
                                        </div>
                                        {rErrors.confirm && <p className="text-xs font-medium mt-1" style={{ color: '#ef4444' }}>{rErrors.confirm}</p>}
                                    </div>

                                    <button
                                        type="submit" disabled={rLoading}
                                        className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold text-white transition-all duration-200 disabled:opacity-50 mt-2"
                                        style={{ background: 'linear-gradient(135deg,#dc2626,#f97316)', boxShadow: '0 4px 20px rgba(220,38,38,0.4)' }}
                                        onMouseEnter={e => { if (!rLoading) (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-2px)' }}
                                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)' }}
                                    >
                                        {rLoading ? <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Sending…</> : "Request access →"}
                                    </button>
                                </form>

                                <p className="text-sm text-center mt-5" style={{ color: '#64748b' }}>
                                    Already have an account?{' '}
                                    <button onClick={() => setMode('login')} className="font-bold transition-colors" style={{ color: '#dc2626' }}>Log in</button>
                                </p>
                            </>
                        )}
                    </div>
                </div>

                {/* ════ PUB PANEL — le rideau qui glisse (suit le thème) ═══════ */}
                <div className={`pub ${mode}`} style={{ background: pub.bg, transition: 'background 0.3s ease' }}>

                    {/* Grid bg animé */}
                    <div className="absolute inset-0 pointer-events-none overflow-hidden">
                        <div className="absolute inset-0 grid-scroll" style={{ backgroundImage: `linear-gradient(${pub.gridLine} 1px,transparent 1px),linear-gradient(90deg,${pub.gridLine} 1px,transparent 1px)`, backgroundSize: '40px 40px', opacity: 1 }} />
                    </div>

                    {/* Orbs */}
                    <div className="absolute top-[-15%] right-[-10%] w-[500px] h-[500px] rounded-full pointer-events-none orb1" style={{ background: `radial-gradient(circle,${pub.orb1} 0%,transparent 65%)` }} />
                    <div className="absolute bottom-[-10%] left-[-8%] w-[380px] h-[380px] rounded-full pointer-events-none orb2" style={{ background: `radial-gradient(circle,${pub.orb2} 0%,transparent 65%)` }} />
                    <div className="absolute top-[40%] left-[10%] w-[200px] h-[200px] rounded-full pointer-events-none orb3" style={{ background: `radial-gradient(circle,${pub.orb3} 0%,transparent 65%)` }} />

                    {/* Scan line */}
                    <div className="absolute left-0 right-0 h-px pointer-events-none scan-line" style={{ background: `linear-gradient(90deg,transparent,${pub.scanLine},transparent)`, zIndex: 5 }} />

                    {/* Top shimmer border */}
                    <div className="absolute top-0 left-0 right-0 h-px" style={{ background: `linear-gradient(90deg,transparent,${pub.topShimmer},transparent)` }} />

                    <div className="relative flex flex-col h-full px-10 py-6 z-10">

                        {/* Badge + theme toggle */}
                        <div className="flex items-center justify-end gap-2 mb-6">
                            <button
                                type="button"
                                onClick={toggleTheme}
                                title={isDarkPub ? 'Light mode' : 'Dark mode'}
                                aria-label={isDarkPub ? 'Switch to light mode' : 'Switch to dark mode'}
                                className="p-1.5 rounded-full transition hover:opacity-80 cursor-pointer"
                                style={{ background: pub.toggleBg, border: `1px solid ${pub.toggleBorder}` }}
                            >
                                {isDarkPub ? <Sun size={13} color="#fbbf24" /> : <Moon size={13} color="#64748b" />}
                            </button>
                            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold"
                                style={{ background: pub.versionBg, border: `1px solid ${pub.versionBorder}`, color: pub.versionText }}>
                                <span className="w-1.5 h-1.5 rounded-full bg-[#fb923c] pdot" />v1.0.0
                            </div>
                        </div>

                        {/* Headline */}
                        <div className="mb-5">
                            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold mb-3 badge-glow"
                                style={{ background: pub.eyebrowBg, border: `1px solid ${pub.eyebrowBorder}`, color: pub.eyebrowText }}>
                                <Activity size={11} /> API Intelligence Platform
                            </div>
                            <h1 className="font-black leading-[1.1] tracking-tight mb-2" style={{ fontSize: '2rem', color: pub.headline }}>
                                Reverse engineer<br />
                                <span style={{ background: 'linear-gradient(135deg,#dc2626,#f97316)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                                    any REST API.
                                </span>
                            </h1>
                            <p className="text-sm leading-relaxed" style={{ color: pub.body, maxWidth: '38ch' }}>
                                Import HAR files, capture live traffic, and let AI automatically generate complete OpenAPI documentation.
                            </p>
                        </div>

                        {/* Stats row */}
                        <div className="grid grid-cols-3 gap-3 mb-5">
                            {[
                                { icon: GitBranch, val: 247, suffix: '', label: 'Endpoints', color: MC.GET },
                                { icon: Shield, val: 99, suffix: '%', label: 'Coverage', color: MC.POST },
                                { icon: Cpu, val: 1247, suffix: '', label: 'LLM Calls', color: MC.PATCH },
                            ].map(({ icon: Icon, val, suffix, label, color }) => (
                                <div key={label} className="rounded-2xl p-3 shimmer relative overflow-hidden"
                                    style={{ background: pub.statCardBg, border: `1px solid ${pub.statCardBorder}` }}>
                                    <Icon size={14} style={{ color, marginBottom: 6 }} />
                                    <div className="text-lg font-black leading-none tick" style={{ color: pub.statValue }} key={mode}>
                                        <Counter to={val} suffix={suffix} />
                                    </div>
                                    <div className="text-[10px] mt-1 font-medium" style={{ color: pub.statLabel }}>{label}</div>
                                </div>
                            ))}
                        </div>

                        {/* ─── Live capture terminal ─────────────────────────── */}
                        <div className="flex-1 min-h-0 rounded-2xl overflow-hidden flex flex-col"
                            style={{ background: pub.terminalBg, border: `1px solid ${pub.terminalBorder}`, backdropFilter: 'blur(20px)' }}>

                            {/* Title bar */}
                            <div className="flex items-center justify-between px-4 py-3 flex-shrink-0"
                                style={{ borderBottom: `1px solid ${pub.terminalHeaderBorder}`, background: pub.terminalHeaderBg }}>
                                <div className="flex items-center gap-2">
                                    <div className="flex gap-1.5">
                                        <span className="w-3 h-3 rounded-full" style={{ background: '#ff5f57' }} />
                                        <span className="w-3 h-3 rounded-full" style={{ background: '#febc2e' }} />
                                        <span className="w-3 h-3 rounded-full" style={{ background: '#28c840' }} />
                                    </div>
                                    <span className="text-xs font-bold ml-1" style={{ color: pub.terminalTitle, fontFamily: "'JetBrains Mono',monospace" }}>aria · live capture</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full" style={{ background: pub.recordingBg, border: `1px solid ${pub.recordingBorder}` }}>
                                        <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] pdot" />
                                        <span className="text-[10px] font-bold" style={{ color: pub.recordingText }}>RECORDING</span>
                                    </div>
                                </div>
                            </div>

                            {/* Column headers */}
                            <div className="flex items-center gap-2 px-4 py-2 flex-shrink-0"
                                style={{ borderBottom: `1px solid ${pub.colHeaderBorder}`, background: pub.colHeaderBg }}>
                                {['METHOD', 'PATH', 'STATUS', 'LATENCY'].map((h, i) => (
                                    <div key={h} className="text-[10px] font-black uppercase tracking-widest"
                                        style={{ color: pub.colHeaderText, width: i === 0 ? '60px' : i === 1 ? '1fr' : i === 2 ? '52px' : '58px', flex: i === 1 ? 1 : undefined }}>
                                        {h}
                                    </div>
                                ))}
                            </div>

                            {/* Log rows */}
                            <div className="flex-1 overflow-hidden px-4 py-2 space-y-1.5">
                                {visibleLogs.map((row, i) => (
                                    <div key={`${row.path}-${i}`} className="log-row flex items-center gap-2 py-1.5 px-3 rounded-xl"
                                        style={{ background: i === visibleLogs.length - 1 ? pub.rowHighlightBg : 'transparent', border: i === visibleLogs.length - 1 ? `1px solid ${pub.rowHighlightBorder}` : '1px solid transparent' }}>
                                        <span className="w-[60px] text-[11px] font-black flex-shrink-0" style={{ color: MC[row.method] ?? pub.statLabel, fontFamily: "'JetBrains Mono',monospace" }}>{row.method}</span>
                                        <span className="flex-1 text-[11px] truncate" style={{ color: pub.pathText, fontFamily: "'JetBrains Mono',monospace" }}>{row.path}</span>
                                        <span className="w-[52px] text-[11px] font-bold text-center flex-shrink-0" style={{ color: row.ok ? pub.recordingText : MC.GET, fontFamily: "'JetBrains Mono',monospace" }}>{row.status}</span>
                                        <span className="w-[58px] text-[11px] text-right flex-shrink-0" style={{ color: pub.latencyText, fontFamily: "'JetBrains Mono',monospace" }}>{row.ms}ms</span>
                                    </div>
                                ))}
                            </div>

                            {/* Footer stats bar */}
                            <div className="flex items-center justify-between px-4 py-3 flex-shrink-0"
                                style={{ borderTop: `1px solid ${pub.footerTop}`, background: pub.footerBg }}>
                                <div className="flex items-center gap-4">
                                    {[
                                        { label: 'Requests', val: '1,247', color: MC.GET },
                                        { label: 'Errors', val: '3', color: MC.DELETE },
                                        { label: 'Avg.', val: '142ms', color: MC.POST },
                                    ].map(({ label, val, color }) => (
                                        <div key={label} className="flex items-center gap-1.5">
                                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />
                                            <span className="text-[10px] font-bold" style={{ color: pub.footerLabel }}>{label}</span>
                                            <span className="text-[10px] font-black" style={{ color: pub.footerValue, fontFamily: "'JetBrains Mono',monospace" }}>{val}</span>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex items-center gap-1 text-[10px]" style={{ color: pub.poweredText }}>
                                    <Zap size={10} />
                                    <span style={{ fontFamily: "'JetBrains Mono',monospace" }}>powered by groq</span>
                                </div>
                            </div>
                        </div>

                        {/* Bottom */}
                        <div className="flex items-center justify-between mt-6">
                            <p className="text-[11px]" style={{ color: pub.copyrightText }}>© 2026 ARIA · Final Year Project by Syrine Majdoub</p>
                            <div className="flex items-center gap-1.5 text-[10px] font-bold px-2.5 py-1 rounded-full"
                                style={{ background: pub.bottomBadgeBg, border: `1px solid ${pub.bottomBadgeBorder}`, color: pub.bottomBadgeText }}>
                                <BarChart2 size={9} /> ARIA v1.0
                            </div>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    )
}
