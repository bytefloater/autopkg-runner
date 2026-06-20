/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './webapp/templates/**/*.html',
    './webapp/static/js/**/*.js',
  ],
  theme: {
    extend: {
      // System font stack used by the mobile layout
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  // Log-level colour classes are only referenced inside JS objects (levelClass()),
  // so the static scanner will miss them. Safelisting ensures the rules are always emitted.
  safelist: [
    'text-gray-400', 'text-gray-500', 'dark:text-gray-500',
    'text-blue-600', 'dark:text-blue-400',
    'text-yellow-600', 'dark:text-yellow-400',
    'text-red-600', 'dark:text-red-400',
    'text-red-700', 'dark:text-red-300',
  ],
}
