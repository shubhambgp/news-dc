// Runs before the app bundle so the first paint already has the right theme (no white flash).
// External file, not inline: the CSP is `script-src 'self'`. Mirrors src/lib/theme.tsx.
try {
  var t = localStorage.getItem('newsdc-theme')
  if (t === 'dark' || (t !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches))
    document.documentElement.classList.add('dark')
} catch {
  // storage blocked: the app falls back to the system theme after load
}
