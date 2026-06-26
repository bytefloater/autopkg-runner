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
  // Colour classes only referenced inside JS objects or filters (levelClass(), statusColor())
  // aren't scanned. Safelisting ensures the rules are always emitted.
  safelist: [
    // Dialog system z-index (used in webapp/templates/webapp/includes/)
    'z-[500]',
    // Log levels
    'text-gray-400', 'text-gray-500', 'dark:text-gray-500',
    'text-blue-600', 'dark:text-blue-400',
    'text-yellow-600', 'dark:text-yellow-400',
    'text-red-600', 'dark:text-red-400',
    'text-red-700', 'dark:text-red-300',
    // Status bubbles
    'bg-gray-900', 'bg-blue-900', 'bg-green-900', 'bg-red-900', 'bg-yellow-900', 'bg-amber-900',
    'dark:bg-gray-900', 'dark:bg-blue-900', 'dark:bg-green-900', 'dark:bg-red-900', 'dark:bg-yellow-900', 'dark:bg-amber-900',
    'dark:text-gray-200', 'dark:text-gray-300',
    'dark:text-blue-200', 'dark:text-green-200', 'dark:text-red-200', 'dark:text-yellow-200', 'dark:text-amber-200',
    // Alert/info box borders
    'dark:border-red-700', 'dark:border-green-700', 'dark:border-amber-700',
  ],
}
