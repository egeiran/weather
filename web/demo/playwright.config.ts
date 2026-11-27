import { defineConfig, devices } from '@playwright/test';

/** Visual self-check: renders the demo and writes docs/screenshots/*.jpg. Needs pipeline output. */
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  workers: 2,
  reporter: [['list']],
  outputDir: '../../.work/playwright-output',
  use: {
    baseURL: 'http://localhost:5173',
    ...devices['Desktop Chrome'],
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    launchOptions: {
      // Real GPU via Metal on macOS (realistic particles); software WebGL elsewhere.
      args:
        process.platform === 'darwin'
          ? ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist']
          : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
    },
  },
  webServer: {
    command: 'npm run dev:web',
    cwd: '../..',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
