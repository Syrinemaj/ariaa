import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Mail, ArrowLeft, CheckCircle2 } from 'lucide-react'

const ARIALogo: React.FC = () => (
  <svg width="40" height="44" viewBox="0 0 36 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="logoGradFP" x1="2" y1="2" x2="34" y2="38" gradientUnits="userSpaceOnUse">
        <stop stopColor="#6366f1" />
        <stop offset="1" stopColor="#8b5cf6" />
      </linearGradient>
    </defs>
    <path d="M18 2L34 11V29L18 38L2 29V11L18 2Z" fill="url(#logoGradFP)" opacity="0.2" />
    <path d="M18 7L30 14V26L18 33L6 26V14L18 7Z" fill="url(#logoGradFP)" />
  </svg>
)

const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    setLoading(true)
    await new Promise((r) => setTimeout(r, 1000))
    setLoading(false)
    setSubmitted(true)
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden" style={{ background: '#0d0f1b' }}>
      <div className="absolute top-[-8%] right-[-4%] w-[480px] h-[480px] rounded-full animate-blob pointer-events-none" style={{ background: '#6366f1', opacity: 0.18, filter: 'blur(90px)' }} />
      <div className="absolute bottom-[-10%] left-[-6%] w-[400px] h-[400px] rounded-full animate-blob-delay pointer-events-none" style={{ background: '#8b5cf6', opacity: 0.15, filter: 'blur(80px)' }} />
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.5) 1px, transparent 1px)', backgroundSize: '28px 28px', opacity: 0.07 }} />

      <div className="relative w-full max-w-md animate-fade-up">
        <div className="rounded-2xl px-8 py-9" style={{ background: '#13151f', border: '1px solid rgba(255,255,255,0.08)', boxShadow: '0 8px 40px rgba(0,0,0,0.4)' }}>
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <ARIALogo />
            <span className="text-3xl font-bold tracking-tight mt-3" style={{ background: 'linear-gradient(135deg, #818cf8, #c4b5fd)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>aria</span>
            <p className="text-sm mt-1 font-medium" style={{ color: 'rgba(255,255,255,0.4)' }}>Intelligence API Inversée</p>
          </div>

          {submitted ? (
            /* État de succès */
            <div className="flex flex-col items-center text-center animate-fade-up">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-4" style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
                <CheckCircle2 size={28} style={{ color: '#22c55e' }} />
              </div>
              <h2 className="text-lg font-semibold mb-2" style={{ color: '#e2e8f0' }}>Vérifiez votre boîte mail</h2>
              <p className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.45)' }}>Nous avons envoyé un lien de réinitialisation à</p>
              <p className="text-sm font-semibold mb-6" style={{ color: '#818cf8' }}>{email}</p>
              <p className="text-xs mb-6" style={{ color: 'rgba(255,255,255,0.3)' }}>Vous ne l'avez pas reçu ? Vérifiez vos spams ou réessayez dans quelques minutes.</p>
              <Link to="/" className="text-sm font-medium flex items-center gap-1.5 transition-colors" style={{ color: '#818cf8' }}>
                <ArrowLeft size={14} />
                Retour à la connexion
              </Link>
            </div>
          ) : (
            /* Formulaire */
            <>
              <div className="mb-6">
                <h2 className="text-xl font-semibold mb-1" style={{ color: '#e2e8f0' }}>Réinitialisez votre mot de passe</h2>
                <p className="text-sm" style={{ color: 'rgba(255,255,255,0.45)' }}>Entrez votre email et nous vous enverrons un lien de réinitialisation.</p>
              </div>
              <form onSubmit={handleSubmit} noValidate>
                <div className="mb-6">
                  <label htmlFor="email" className="block text-sm font-medium mb-1.5" style={{ color: '#94a3b8' }}>Adresse email</label>
                  <div className="relative">
                    <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#94a3b8] pointer-events-none" />
                    <input
                      id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                      placeholder="vous@exemple.com" autoComplete="email" required
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm text-white placeholder-[rgba(255,255,255,0.3)] bg-[#1a1d2e] transition-all duration-150"
                      style={{ border: '1.5px solid rgba(255,255,255,0.1)', outline: 'none' }}
                      onFocus={(e) => (e.currentTarget.style.borderColor = '#6366f1')}
                      onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')}
                    />
                  </div>
                </div>
                <button
                  type="submit" disabled={loading || !email}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                  style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.35)' }}
                  onMouseEnter={(e) => { if (!loading) e.currentTarget.style.transform = 'translateY(-2px)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)' }}
                >
                  {loading ? (
                    <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>Envoi en cours…</>
                  ) : 'Envoyer le lien'}
                </button>
              </form>
              <div className="text-center mt-6">
                <Link to="/" className="text-sm font-medium flex items-center justify-center gap-1.5 transition-colors" style={{ color: '#818cf8' }}>
                  <ArrowLeft size={14} />
                  Retour à la connexion
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

export default ForgotPasswordPage
