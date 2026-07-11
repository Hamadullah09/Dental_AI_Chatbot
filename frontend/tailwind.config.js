/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      colors: {
        dental: {
          accent: 'var(--dental-accent)',
          accentHover: 'var(--dental-accentHover)',
          accentSoft: 'var(--dental-accentSoft)',
          darkBg: 'var(--dental-darkBg)',
          sidebar: 'var(--dental-sidebar)',
          card: 'var(--dental-card)',
          elevated: 'var(--dental-elevated)',
          input: 'var(--dental-input)',
          muted: 'var(--dental-muted)',
          border: 'var(--dental-border)',
          borderStrong: 'var(--dental-borderStrong)',
          textPrimary: 'var(--dental-textPrimary)',
          textSecondary: 'var(--dental-textSecondary)',
          textMuted: 'var(--dental-textMuted)',
          userBubble: 'var(--dental-userBubble)',
          userBubbleText: 'var(--dental-userBubbleText)',
        }
      },
      boxShadow: {
        dental: 'var(--dental-shadow)',
      }
    },
  },
  plugins: [],
}
