/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 6 classification (Phase 1A: 引用 CSS 变量而非硬编码)
        'cat-ai':       'var(--color-ai)',
        'cat-security': 'var(--color-security)',
        'cat-finance':  'var(--color-finance)',
        'cat-startup':  'var(--color-startup)',
        'cat-bid':      'var(--color-bid)',
        'cat-general':  'var(--color-general)',
        // Semantic state (Phase 1A 补强)
        'success': 'var(--color-success)',
        'warning': 'var(--color-warning)',
        'error':   'var(--color-error)',
        'info':    'var(--color-info)',
        // Surfaces (Phase 1A: 保留 dark- 前缀兼容现有组件)
        'dark-bg':      'var(--bg-primary)',
        'dark-card':    'var(--bg-card)',
        'dark-hover':   'var(--bg-hover)',
        'dark-elevated':'var(--bg-elevated)',
        'dark-border':  'var(--border-color)',
        // Accents (兼容旧 dark-xxx 别名, Phase 1B 后逐步移除)
        'accent-cyan':   'var(--color-ai)',
        'accent-red':    'var(--color-security)',
        'accent-gold':   'var(--color-finance)',
        'accent-purple': 'var(--color-startup)',
        'accent-orange': 'var(--color-bid)',
        'accent-green':  'var(--color-general)',
        // Text
        'text-main':       'var(--text-primary)',
        'text-secondary':  'var(--text-secondary)',
        'text-muted':      'var(--text-muted)',
      },
      fontFamily: {
        // Phase 7: 区分 sans (UI body) 与 mono (data/code)
        // 不再混用 — 解决「全部 mono 看起来像 terminal」问题
        'sans': [
          'Inter',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'PingFang SC',
          'Hiragino Sans GB',
          'Microsoft YaHei',
          'sans-serif',
        ],
        'mono': [
          'JetBrains Mono',
          'Fira Code',
          'Cascadia Code',
          'monospace',
        ],
        // Knowledge 阅读模式保留衬线 (未来 Phase 3 启用)
        'serif': ['Newsreader', 'Iowan Old Style', 'Apple Garamond', 'serif'],
      },
      // Phase 7: 标准字重 + 字距
      fontWeight: {
        normal:  '400',
        medium:  '500',
        semibold:'600',
        bold:    '700',
      },
      letterSpacing: {
        tightest: '-0.02em',
        tight:    '-0.01em',
        normal:   '0',
        wide:     '0.04em',
        wider:    '0.08em',
      },
      // Phase 7: 5 级行高
      lineHeight: {
        tight:   '1.3',
        snug:    '1.4',
        normal:  '1.5',
        relaxed: '1.6',
      },
      // Phase 7: 5 级字号 (与 .text-*-tech 对齐)
      fontSize: {
        'xs':   ['12px', { lineHeight: '1.5' }],
        'sm':   ['14px', { lineHeight: '1.5' }],
        'base': ['16px', { lineHeight: '1.5' }],
        'lg':   ['20px', { lineHeight: '1.4' }],
        'xl':   ['24px', { lineHeight: '1.3' }],
      },
      borderRadius: {
        'sm':   'var(--radius-sm)',
        'md':   'var(--radius-md)',
        'lg':   'var(--radius-lg)',
        'full': 'var(--radius-full)',
      },
      boxShadow: {
        'card':     'var(--shadow-card)',
        'elevated': 'var(--shadow-elevated)',
        'popover':  'var(--shadow-popover)',
        'modal':    'var(--shadow-modal)',
        'toast':    'var(--shadow-toast)',
      },
      spacing: {
        '0':  'var(--space-0)',
        '1':  'var(--space-1)',
        '2':  'var(--space-2)',
        '3':  'var(--space-3)',
        '4':  'var(--space-4)',
        '5':  'var(--space-5)',
        '6':  'var(--space-6)',
        '7':  'var(--space-7)',
        '8':  'var(--space-8)',
      },
      zIndex: {
        'base':     'var(--z-base)',
        'dropdown': 'var(--z-dropdown)',
        'sticky':   'var(--z-sticky)',
        'overlay':  'var(--z-overlay)',
        'modal':    'var(--z-modal)',
        'popover':  'var(--z-popover)',
        'toast':    'var(--z-toast)',
        'tooltip':  'var(--z-tooltip)',
      },
      transitionDuration: {
        'fast':   'var(--duration-fast)',
        'normal': 'var(--duration-normal)',
        'slow':   'var(--duration-slow)',
      },
      transitionTimingFunction: {
        'out':    'var(--ease-out)',
        'in-out': 'var(--ease-in-out)',
      },
    },
  },
  plugins: [],
}
