/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#14232B',
        muted: '#5B7079',
        field: '#EDF1F3',
        rule: '#C9D6DB',
        paper: '#FFFFFF',
        evidence: '#1F6F5C',
        gap: '#B4651A',
        focus: '#2A4E8F',
        band: {
          required: '#1F6F5C',
          semantic: '#2A4E8F',
          keywords: '#4C8C7B',
          project: '#3D6EA8',
          education: '#7A9A4F',
          certification: '#B4651A',
          soft: '#8A6FA8',
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        micro: ['0.6875rem', { lineHeight: '1rem' }],
      },
    },
  },
  plugins: [],
}
