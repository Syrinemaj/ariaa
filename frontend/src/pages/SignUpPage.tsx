import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { User, Mail, Lock, Eye, EyeOff, CheckCircle2, Info, AlertCircle } from 'lucide-react'
import { api, ApiError } from '../lib/api'


interface FormErrors {
  full_name?: string
  email?: string
  password?: string
  confirmPassword?: string
}

const FEATURES = [
  'Rétro-ingénierie des endpoints API avec précision',
  "Contrôle d'accès par rôle & approbations d'équipe",
  'Surveillance des sessions en temps réel & alertes de sécurité',
]

const SignUpPage: React.FC = () => {
  const [fullName, setFullName]             = useState('')
  const [email, setEmail]                   = useState('')
  const [password, setPassword]             = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword]     = useState(false)
  const [showConfirm, setShowConfirm]       = useState(false)
  const [loading, setLoading]               = useState(false)
  const [submitted, setSubmitted]           = useState(false)
  const [apiError, setApiError]             = useState('')
  const [errors, setErrors]                 = useState<FormErrors>({})

  const validate = (): boolean => {
    const newErrors: FormErrors = {}
    if (!fullName.trim() || fullName.trim().length < 2)
      newErrors.full_name = 'Le nom doit contenir au moins 2 caractères.'
    if (!email.includes('@'))
      newErrors.email = 'Veuillez entrer une adresse email valide.'
    if (password.length < 8)
      newErrors.password = 'Le mot de passe doit contenir au moins 8 caractères.'
    if (password !== confirmPassword)
      newErrors.confirmPassword = 'Les mots de passe ne correspondent pas.'
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setApiError('')
    if (!validate()) return
    setLoading(true)
    try {
      await api.post('/auth/request-access', {
        email,
        password,
        full_name: fullName.trim(),
      })
      setSubmitted(true)
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 422) {
          setApiError('Veuillez vérifier les informations saisies.')
        } else if (err.status === 429) {
          setApiError('Trop de tentatives. Réessayez dans quelques minutes.')
        } else if (err.status === 404) {
          setApiError('Service indisponible. Vérifiez que le serveur est démarré.')
        } else {
          setApiError('Une erreur est survenue. Veuillez réessayer.')
        }
      } else {
        setApiError('Erreur réseau. Vérifiez votre connexion.')
      }
    } finally {
      setLoading(false)
    }
  }

  const inputBase = "w-full pl-10 pr-4 py-2.5 rounded-xl text-sm text-white placeholder-[rgba(255,255,255,0.3)] bg-[#1a1d2e] transition-all duration-150"
  const inputStyle = { border: '1.5px solid rgba(255,255,255,0.1)', outline: 'none' }
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = '#6366f1')
  const onBlur  = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')

  return (
    <div className="min-h-[100dvh] flex flex-col lg:flex-row">
      {/* ── Left brand panel ─────────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between lg:w-[52%] px-14 py-12 relative overflow-hidden" style={{ background: '#0d0f1b' }}>
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.045) 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />
        <div className="absolute top-0 left-0 right-0 h-px" style={{ background: 'linear-gradient(90deg, transparent, rgba(2,132,199,0.5), transparent)' }} />

        <div className="relative">
          <div className="flex items-center gap-3 mb-16">
            <img src="/logo.png" alt="ARIA" style={{ height: 30, width: 'auto' }} />
            <span className="text-lg font-semibold tracking-tight" style={{ color: '#1E318A' }}>aria</span>
          </div>

          <h1 className="text-4xl font-bold text-white tracking-tight leading-tight mb-4">
            Demandez l'accès<br />à la plateforme.
          </h1>
          <p className="text-sm text-zinc-400 leading-relaxed max-w-[48ch] mb-10">
            Soumettez votre demande et un manager examinera votre dossier pour vous attribuer un rôle.
          </p>

          <div className="space-y-3.5">
            {FEATURES.map((f) => (
              <div key={f} className="flex items-center gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-500 flex-shrink-0" />
                <span className="text-sm text-zinc-300">{f}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>© 2026 ARIA · PFE</p>
      </div>

      {/* ── Right form panel ─────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center px-8 sm:px-14 py-12 min-h-[100dvh] lg:min-h-0" style={{ background: '#0d0f1b' }}>
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-2.5 mb-10">
          <img src="/logo.png" alt="ARIA" style={{ height: 28, width: 'auto' }} />
          <span className="text-lg font-semibold tracking-tight" style={{ color: '#1E318A' }}>aria</span>
        </div>

        <div className="w-full max-w-sm">
          {submitted ? (
            <div className="flex flex-col items-start animate-fade-up py-4">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-5" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
                <CheckCircle2 size={24} style={{ color: '#16a34a' }} />
              </div>
              <h2 className="text-2xl font-bold tracking-tight mb-2" style={{ color: '#e2e8f0' }}>Demande envoyée</h2>
              <p className="text-sm mb-5" style={{ color: 'rgba(255,255,255,0.45)' }}>Votre demande de compte a été reçue et est en cours d'examen. Un manager vous assignera un rôle.</p>
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold mb-6" style={{ background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)', color: '#fbbf24' }}>
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                En attente d'approbation
              </span>
              <Link to="/" className="text-sm font-medium transition-colors" style={{ color: '#818cf8' }}>
                Retour à la connexion
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-2xl font-bold tracking-tight mb-1" style={{ color: '#e2e8f0' }}>Créer un compte</h2>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>Remplissez vos informations pour demander l'accès.</p>
              </div>

              {/* Bannière d'information */}
              <div className="flex items-start gap-3 rounded-xl px-4 py-3 mb-5 text-sm" style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}>
                <Info size={15} style={{ color: '#818cf8', marginTop: 1, flexShrink: 0 }} />
                <p className="text-xs leading-relaxed" style={{ color: 'rgba(255,255,255,0.55)' }}>Un manager examinera votre demande et vous assignera un rôle avant que vous puissiez accéder à la plateforme.</p>
              </div>

              {apiError && (
                <div className="flex items-center gap-2 rounded-xl px-4 py-3 mb-4" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                  <AlertCircle size={15} style={{ color: '#f87171', flexShrink: 0 }} />
                  <p className="text-xs" style={{ color: '#f87171' }}>{apiError}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {/* Nom complet */}
                <div>
                  <label htmlFor="full_name" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>Nom complet</label>
                  <div className="relative">
                    <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    <input id="full_name" type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Prénom Nom" autoComplete="name" className={inputBase} style={inputStyle} onFocus={onFocus} onBlur={onBlur} />
                  </div>
                  {errors.full_name && <p className="text-xs text-red-500 mt-1">{errors.full_name}</p>}
                </div>

                {/* Email */}
                <div>
                  <label htmlFor="su-email" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>Adresse email</label>
                  <div className="relative">
                    <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    <input id="su-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="vous@exemple.com" autoComplete="email" className={inputBase} style={inputStyle} onFocus={onFocus} onBlur={onBlur} />
                  </div>
                  {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email}</p>}
                </div>

                {/* Mot de passe */}
                <div>
                  <label htmlFor="su-password" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>Mot de passe</label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    <input id="su-password" type={showPassword ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min. 8 caractères" autoComplete="new-password" className={`${inputBase} pr-10`} style={inputStyle} onFocus={onFocus} onBlur={onBlur} />
                    <button type="button" className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer transition-colors" onClick={() => setShowPassword(!showPassword)}>
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  {errors.password && <p className="text-xs text-red-500 mt-1">{errors.password}</p>}
                </div>

                {/* Confirmer le mot de passe */}
                <div>
                  <label htmlFor="su-confirm" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>Confirmer le mot de passe</label>
                  <div className="relative">
                    <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    <input id="su-confirm" type={showConfirm ? 'text' : 'password'} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Répéter le mot de passe" autoComplete="new-password" className={`${inputBase} pr-10`} style={inputStyle} onFocus={onFocus} onBlur={onBlur} />
                    <button type="button" className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer transition-colors" onClick={() => setShowConfirm(!showConfirm)}>
                      {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  {errors.confirmPassword && <p className="text-xs text-red-500 mt-1">{errors.confirmPassword}</p>}
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 cursor-pointer disabled:opacity-55 mt-2"
                  style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', boxShadow: '0 4px 20px rgba(99,102,241,0.4)' }}
                  onMouseEnter={(e) => { if (!loading) e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)' }}
                  onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)' }}
                  onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)' }}
                >
                  {loading ? (
                    <>
                      <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      Envoi en cours…
                    </>
                  ) : 'Demander l\'accès'}
                </button>
              </form>

              <p className="text-sm mt-5" style={{ color: 'rgba(255,255,255,0.4)' }}>
                Déjà un compte ?{' '}
                <Link to="/" className="font-medium transition-colors" style={{ color: '#818cf8' }}>Se connecter</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default SignUpPage
