import { defineConfig } from '@playwright/test'

// One smoke test (PLAN Phase 9). The API is mocked in the test, so no backend or DB is needed.
export default defineConfig({
  testDir: 'e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: 'http://localhost:4174',
    // Locally use the installed Chrome; CI installs Playwright's Chromium.
    channel: process.env.CI ? undefined : 'chrome',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm exec vite --port 4174 --strictPort',
    url: 'http://localhost:4174',
    reuseExistingServer: !process.env.CI,
    env: { VITE_API_BASE_URL: '' },
  },
})
