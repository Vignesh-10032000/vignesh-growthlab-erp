import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../test-results/playwright',
  reporter: [['list'], ['html', { outputFolder: '../test-results/playwright-report', open: 'never' }]],
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5197', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } },
             { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5197 --strictPort',
    env: { ERP_API_PROXY: 'http://127.0.0.1:8001' },
    url: 'http://127.0.0.1:5197',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
})
