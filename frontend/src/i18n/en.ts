import type { hu } from './hu'

// A típus a magyar szótárból jön: ha ott új kulcs lesz, itt fordítási hiba jelzi a hiányt.
export const en: typeof hu = {
  app: {
    tagline: 'Chronic care remote patient monitoring platform',
    disclaimer:
      'Demonstration system using synthetic data only. Not a medical device and does not replace clinical judgement.',
  },
  health: {
    title: 'System status',
    checking: 'Checking…',
    ok: 'The API and the database are reachable.',
    error: 'The API is not reachable.',
  },
}
