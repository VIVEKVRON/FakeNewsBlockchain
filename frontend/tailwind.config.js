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
        background: 'rgb(var(--background) / <alpha-value>)',
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        card: {
          DEFAULT: 'rgb(var(--card) / <alpha-value>)',
          foreground: 'rgb(var(--card-foreground) / <alpha-value>)',
        },
        border: 'rgb(var(--border) / <alpha-value>)',
        navy: {
          950: '#020B16',
          900: '#061321',
          850: '#0A1B2B',
        },
        brand: {
          blue: '#087BFF',
          cyan: '#00C8FF',
          violet: '#6366f1',
          purple: '#8b5cf6',
        },
        verdict: {
          genuine: '#10b981',
          fake: '#f43f5e',
          misleading: '#f59e0b',
          partial: '#6366f1',
          outdated: '#f97316',
          unverified: '#64748b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'glow-cyan': '0 0 24px -4px rgba(0, 200, 255, 0.28)',
        'glow-blue': '0 0 22px -4px rgba(8, 123, 255, 0.30)',
        'glow-violet': '0 0 22px -4px rgba(99, 102, 241, 0.28)',
        'glow-emerald': '0 0 20px -4px rgba(16, 185, 129, 0.24)',
        'glow-rose': '0 0 20px -4px rgba(244, 63, 94, 0.24)',
        'glass-dark': '0 18px 42px -18px rgba(0, 0, 0, 0.72), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
        'glass-light': '0 14px 36px -16px rgba(15, 23, 42, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.85)',
      }
    },
  },
  plugins: [],
}
