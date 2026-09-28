import defaultTheme from 'tailwindcss/defaultTheme'
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', ...defaultTheme.fontFamily.sans] },
      colors: {
        ui: {
          bg:            'var(--ui-bg-base)',
          surface:       'var(--ui-bg-surface)',
          elevated:      'var(--ui-bg-elevated)',
          hover:         'var(--ui-bg-hover)',
          selected:      'var(--ui-bg-selected)',
          border:        'var(--ui-border)',
          'border-strong': 'var(--ui-border-strong)',
          text:          'var(--ui-text-primary)',
          'text-2':      'var(--ui-text-secondary)',
          muted:         'var(--ui-text-muted)',
          'on-accent':   'var(--ui-text-on-accent)',
          accent:        'var(--ui-accent)',
          'accent-hover': 'var(--ui-accent-hover)',
          'accent-muted': 'var(--ui-accent-muted)',
          success:       'var(--ui-success)',
          'success-bg':  'var(--ui-success-bg)',
          warning:       'var(--ui-warning)',
          'warning-bg':  'var(--ui-warning-bg)',
          error:         'var(--ui-error)',
          'error-bg':    'var(--ui-error-bg)',
          info:          'var(--ui-info)',
          'info-bg':     'var(--ui-info-bg)',
        },
        brand: {
          50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
          400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8',
          800: '#1e40af', 900: '#1e3a8a',
        },
        surface: {
          DEFAULT: '#ffffff',
          50: '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
        },
      },
      boxShadow: {
        card:     '0 1px 3px 0 rgb(0 0 0 / 0.07), 0 1px 2px -1px rgb(0 0 0 / 0.07)',
        dropdown: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        elevated: '0 4px 6px -1px rgb(0 0 0 / 0.15), 0 2px 4px -2px rgb(0 0 0 / 0.15)',
      },
    },
  },
  plugins: [],
}
