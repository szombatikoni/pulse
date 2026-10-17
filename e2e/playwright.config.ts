// A böngészős folyamatteszt beállításai. A teszt egy már futó, frissen seedelt
// rendszert vár (docker compose up + python -m seed); a CI is így futtatja.
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  // A lépések egymásra épülnek (a beteg rögzít, utána az orvos látja), és
  // módosítják az adatbázist, ezért egyszerre csak egy teszt fut.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.PULSE_URL ?? 'http://localhost:8080',
    // A dátumok, a tizedesvessző és a „ma 07:30" így a CI-ban is ugyanúgy
    // jelenik meg, mint egy magyar gépen.
    locale: 'hu-HU',
    timezoneId: 'Europe/Budapest',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } },
    },
  ],
})
