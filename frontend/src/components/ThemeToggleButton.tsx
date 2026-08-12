import React from 'react'
import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'

/** Floating light/dark toggle for pages rendered before login (no Topbar yet). */
export default function ThemeToggleButton({ style }: { style?: React.CSSProperties }) {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={isDark ? 'Light mode' : 'Dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="fixed top-5 right-5 z-50 p-2.5 rounded-xl transition hover:opacity-80 backdrop-blur-md cursor-pointer"
      style={{
        background: isDark ? 'rgba(255,255,255,0.06)' : '#ffffff',
        border: `1px solid ${isDark ? 'rgba(255,255,255,0.14)' : '#e2e8f0'}`,
        boxShadow: isDark ? 'none' : '0 4px 14px rgba(15,23,42,0.08)',
        ...style,
      }}
    >
      {isDark ? <Sun size={16} color="#fbbf24" /> : <Moon size={16} color="#475569" />}
    </button>
  )
}
