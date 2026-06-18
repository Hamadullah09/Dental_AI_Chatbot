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
          darkBg: 'var(--dental-darkBg)',
          sidebar: 'var(--dental-sidebar)',
          card: 'var(--dental-card)',
          border: 'var(--dental-border)',
          textPrimary: 'var(--dental-textPrimary)',
          textSecondary: 'var(--dental-textSecondary)',
        }
      }
    },
  },
  plugins: [],
}
