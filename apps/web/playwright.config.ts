import { defineConfig, devices } from '@playwright/test'

// Starts GigSim, the API (deterministic fake model, in-process MCP, inline worker) and the web app.
const py = process.env.PYTHON ?? (process.platform === 'win32' ? '.venv/Scripts/python.exe' : 'python')  // commands run from the repo root
const runId = Date.now()

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: { baseURL: 'http://localhost:5174', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone', use: { ...devices['Pixel 7'] }, testMatch: /onboarding/ },
  ],
  webServer: [
    {
      command: `${py} -m uvicorn gigsim.app:app --port 8082`,
      cwd: '../..', port: 8082, reuseExistingServer: false,
      env: { GIGSIM_DB: `logs/e2e_gigsim_${runId}.sqlite`, GIGSIM_ERROR_RATE: '0', GIGSIM_RATE_LIMIT: '100000' },
    },
    {
      command: `${py} scripts/dev_api.py`,
      cwd: '../..', url: 'http://localhost:8001/health', reuseExistingServer: false, timeout: 180_000,
      env: { API_PORT: '8001', MODEL_PROFILE: 'fake', GIGSIM_BASE_URL: 'http://localhost:8082', MARKETPLACE_RPM: '100000',
             WEB_ORIGIN: 'http://localhost:5174', DATABASE_URL: '', REDIS_URL: '', OPEN_LLM_API_KEY: '' },
    },
    {
      command: 'npx vite --port 5174 --strictPort',
      port: 5174, reuseExistingServer: false,
      env: { VITE_API_PROXY: 'http://localhost:8001' },
    },
  ],
})
