import React, { useState, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { Lock, Eye, EyeOff, CheckCircle2, AlertCircle, ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'


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

  // Rediriger vers /forgot-password si pas de token
  useEffect(() => {
    if (!token) navigate('/forgot-password', { replace: true })
  }, [token, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password.length < 8) {
      setError('Le mot de passe doit contenir au moins 8 caractères.')
      return
    }
    if (password !== confirm) {
      setError('Les mots de passe ne correspondent pas.')
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
        setError('Ce lien de réinitialisation est invalide ou a expiré. Veuillez refaire une demande.')
      } else {
        setError('Une erreur est survenue. Veuillez réessayer.')
      }
    } finally {
      setLoading(false)
    }
  }

  const inputBase = "w-full pl-10 pr-10 py-2.5 rounded-xl text-sm text-white placeholder-[rgba(255,255,255,0.3)] bg-[#1a1d2e] transition-all duration-150"
  const inputStyle = { border: '1.5px solid rgba(255,255,255,0.1)', outline: 'none' }
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = '#6366f1')
  const onBlur  = (e: React.FocusEvent<HTMLInputElement>) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden" style={{ background: '#0d0f1b' }}>
      <div className="absolute top-[-8%] right-[-4%] w-[480px] h-[480px] rounded-full animate-blob pointer-events-none" style={{ background: '#6366f1', opacity: 0.18, filter: 'blur(90px)' }} />
      <div className="absolute bottom-[-10%] left-[-6%] w-[400px] h-[400px] rounded-full animate-blob-delay pointer-events-none" style={{ background: '#8b5cf6', opacity: 0.15, filter: 'blur(80px)' }} />
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.5) 1px, transparent 1px)', backgroundSize: '28px 28px', opacity: 0.07 }} />

      <div className="relative w-full max-w-md animate-fade-up">
        <div className="rounded-2xl px-8 py-9" style={{ background: '#13151f', border: '1px solid rgba(255,255,255,0.08)', boxShadow: '0 8px 40px rgba(0,0,0,0.4)' }}>
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <img src="/logo.png" alt="ARIA" style={{ height: 40, width: 'auto' }} />
            <span className="text-3xl font-bold tracking-tight mt-3" style={{ color: '#1E318A' }}>aria</span>
            <p className="text-sm mt-1 font-medium" style={{ color: 'rgba(255,255,255,0.4)' }}>Intelligence API Inversée</p>
          </div>

          {success ? (
            <div className="flex flex-col items-center text-center animate-fade-up">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
                <CheckCircle2 size={28} style={{ color: '#22c55e' }} />
              </div>
              <h2 className="text-lg font-semibold mb-2" style={{ color: '#e2e8f0' }}>Mot de passe modifié !</h2>
              <p className="text-sm mb-6" style={{ color: 'rgba(255,255,255,0.45)' }}>
                Votre mot de passe a été mis à jour avec succès.<br />
                Vous allez être redirigé vers la connexion…
              </p>
              <Link to="/login" className="text-sm font-medium flex items-center gap-1.5 transition-colors" style={{ color: '#818cf8' }}>
                <ArrowLeft size={14} />
                Aller à la connexion
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold mb-1" style={{ color: '#e2e8f0' }}>Nouveau mot de passe</h2>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>
                  Choisissez un nouveau mot de passe sécurisé.
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-2.5 rounded-xl px-4 py-3 mb-5" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                  <AlertCircle size={15} style={{ color: '#f87171', marginTop: 1, flexShrink: 0 }} />
                  <p className="text-xs leading-relaxed" style={{ color: '#f87171' }}>{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-4">
                {/* Nouveau mot de passe */}
                <div>
                  <label htmlFor="rp-password" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>
                    Nouveau mot de passe
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] pointer-events-none" />
                    <input
                      id="rp-password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="Min. 8 caractères"
                      autoComplete="new-password"
                      className={inputBase}
                      style={inputStyle}
                      onFocus={onFocus}
                      onBlur={onBlur}
                    />
                    <button
                      type="button"
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 cursor-pointer transition-colors"
                      style={{ color: '#94a3b8' }}
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
                              ? i === 0 ? '#f59e0b' : i === 1 ? '#22c55e' : '#6366f1'
                              : 'rgba(255,255,255,0.1)',
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {/* Confirmer */}
                <div>
                  <label htmlFor="rp-confirm" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>
                    Confirmer le mot de passe
                  </label>
                  <div className="relative">
                    <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] pointer-events-none" />
                    <input
                      id="rp-confirm"
                      type={showConfirm ? 'text' : 'password'}
                      value={confirm}
                      onChange={e => setConfirm(e.target.value)}
                      placeholder="Répéter le mot de passe"
                      autoComplete="new-password"
                      className={inputBase}
                      style={inputStyle}
                      onFocus={onFocus}
                      onBlur={onBlur}
                    />
                    <button
                      type="button"
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 cursor-pointer transition-colors"
                      style={{ color: '#94a3b8' }}
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
                  style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.35)' }}
                  onMouseEnter={e => { if (!loading) e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)' }}
                >
                  {loading ? (
                    <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Modification en cours…</>
                  ) : 'Changer le mot de passe'}
                </button>
              </form>

              <div className="text-center mt-6">
                <Link to="/forgot-password" className="text-sm font-medium flex items-center justify-center gap-1.5 transition-colors" style={{ color: '#818cf8' }}>
                  <ArrowLeft size={14} />
                  Renvoyer un lien
                </Link>
              </div>
            </>
          )}
        </div>
        <p className="text-center text-xs mt-4" style={{ color: 'rgba(255,255,255,0.2)' }}>© 2026 ARIA · PFE</p>
      </div>
    </div>
  )
}

export default ResetPasswordPage
