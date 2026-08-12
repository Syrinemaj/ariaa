/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'aria-bg': '#f8faff',
        'aria-card': '#ffffff',
        'aria-border': '#e2e8f0',
        'aria-text': '#0f172a',
        'aria-muted': '#64748b',
        'aria-primary': '#dc2626',
        'aria-secondary': '#f97316',
        'aria-success': '#22c55e',
        'aria-error': '#ef4444',
        'aria-warning': '#f59e0b',
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      animation: {
        'fade-up': 'fadeUp 0.5s ease-out both',
        'fade-up-1': 'fadeUp 0.5s 0.1s ease-out both',
        'fade-up-2': 'fadeUp 0.5s 0.2s ease-out both',
        'fade-up-3': 'fadeUp 0.5s 0.3s ease-out both',
        'fade-in': 'fadeIn 0.3s ease-out',
        'blob': 'blob 8s infinite',
        'blob-delay': 'blob 8s 3s infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        blob: {
          '0%': { transform: 'translate(0px, 0px) scale(1)' },
          '33%': { transform: 'translate(30px, -50px) scale(1.1)' },
          '66%': { transform: 'translate(-20px, 20px) scale(0.9)' },
          '100%': { transform: 'translate(0px, 0px) scale(1)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(245, 158, 11, 0.4)' },
          '50%': { boxShadow: '0 0 0 8px rgba(245, 158, 11, 0)' },
        },
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgb(0 0 0 / 0.04), 0 4px 16px -2px rgb(0 0 0 / 0.06)',
        'card-hover': '0 8px 32px -4px rgb(99 102 241 / 0.18)',
      },
    },
  },
  plugins: [],
}
