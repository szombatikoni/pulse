import type { hu } from './hu'

// A típus a magyar szótárból jön: ha ott új kulcs lesz, itt fordítási hiba jelzi a hiányt.
export const en: typeof hu = {
  app: {
    tagline: 'Chronic care remote patient monitoring platform',
    disclaimer:
      'Demonstration system using synthetic data only. Not a medical device and does not replace clinical judgement.',
  },
  login: {
    email: 'Email address',
    password: 'Password',
    submit: 'Sign in',
    invalid: 'Incorrect email address or password.',
    expired: 'Your session has expired. Please sign in again.',
  },
  errors: {
    unavailable: 'The server is not reachable right now. Please try again later.',
  },
  layout: {
    logout: 'Sign out',
  },
  roles: {
    patient: 'Patient',
    doctor: 'Doctor',
    admin: 'Administrator',
  },
  home: {
    patient: {
      title: 'My tasks',
      placeholder: 'Your due measurements and questionnaires will appear here.',
    },
    doctor: {
      title: 'My patients',
      placeholder: 'The prioritised list of your patients will appear here.',
    },
    admin: {
      title: 'Administration',
      placeholder: 'User and doctor–patient assignment management will be here.',
    },
  },
}
