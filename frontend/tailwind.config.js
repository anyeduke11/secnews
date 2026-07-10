/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'dark-bg': 'var(--bg-primary)',
        'dark-card': 'var(--bg-card)',
        'dark-hover': 'var(--bg-hover)',
        'dark-border': 'var(--border-color)',
        'accent-cyan': '#00bcd4',
        'accent-red': '#e85d5d',
        'accent-gold': '#f0c929',
        'accent-purple': '#7c6aff',
        'accent-orange': '#e8891a',
        'accent-green': '#00c96a',
        'text-main': 'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted': 'var(--text-muted)',
      },
      fontFamily: {
        'mono': ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
