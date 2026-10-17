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
    forbidden: 'You do not have access to this patient.',
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
    },
    doctor: {
      title: 'My patients',
    },
    admin: {
      title: 'Administration',
      placeholder: 'User and doctor–patient assignment management will be here.',
    },
  },
  status: {
    severe: 'Severe',
    attention: 'Attention',
    no_data: 'No data',
    handled: 'Handled',
    ok: 'OK',
  },
  severity: {
    moderate: 'moderate',
    severe: 'severe',
  },
  units: {
    mmHg: 'mmHg',
    perMin: '/min',
    kg: 'kg',
    mmolL: 'mmol/L',
  },
  measurementTypes: {
    blood_pressure: 'Blood pressure',
    heart_rate: 'Heart rate',
    body_weight: 'Body weight',
    blood_glucose: 'Blood glucose',
  },
  components: {
    systolic: 'Systolic',
    diastolic: 'Diastolic',
  },
  relative: {
    today: 'today {{time}}',
    yesterday: 'yesterday {{time}}',
    daysAgo_one: '{{count}} day ago',
    daysAgo_other: '{{count}} days ago',
  },
  measurements: {
    newTitle: 'New measurement',
    type: 'Measurement type',
    measuredAt: 'Measured at',
    measuredAtHint: 'Up to two days back.',
    save: 'Save',
    saved: 'Measurement saved.',
    historyTitle: 'My previous measurements',
    empty: 'No measurements recorded yet.',
    columns: {
      time: 'Measured at',
      type: 'Type',
      value: 'Value',
    },
    errors: {
      too_old: 'Measurements can be recorded up to two days back.',
      in_future: 'The measurement time cannot be in the future.',
      out_of_range: 'The {{component}} value is outside the accepted range.',
      missing_value: 'Please also enter: {{component}}.',
      unknown_type: 'Unknown measurement type.',
      unknown_component: 'Unknown value: {{component}}.',
      timezone_required: 'The measurement time needs a time zone.',
      generic: 'The measurement could not be saved.',
    },
  },
  questionnaires: {
    title: 'Questionnaires to complete',
    none: 'No questionnaires are assigned to you at the moment.',
    submit: 'Submit',
    submitted: 'Thank you, your answers have been received.',
    error: 'Your answers could not be submitted.',
    errors: {
      not_assigned: 'This questionnaire is no longer assigned to you.',
      unknown_question: 'The questionnaire has changed; please fill it in again.',
      missing_answer: 'Please answer every question.',
      invalid_answer: 'Invalid answer; please check your responses.',
    },
    lastSubmitted: 'Last completed: {{when}}',
    neverSubmitted: 'Not completed yet.',
    empty: 'No submissions yet.',
    version: 'version {{version}}',
    columns: {
      time: 'Submitted',
      questionnaire: 'Questionnaire',
      score: 'Score',
      band: 'Band',
    },
    bands: {
      normal: 'normal',
      warning: 'warning',
      critical: 'critical',
    },
    scoreSummary: '“{{name}}” questionnaire: {{score}}/{{max}} points ({{band}} band)',
  },
  doctor: {
    columns: {
      status: 'Status',
      patient: 'Patient',
      reason: 'Reason',
      lastData: 'Last data',
    },
    empty: 'No patients are assigned to you at the moment.',
    reasons: {
      open_alert: 'Open alert',
      no_data_yet: 'No data received yet',
      stale_data: 'No recent data',
      fresh_data: 'Last measurement OK',
    },
    back: 'My patients',
    age: '{{age}} years',
    alertsTitle: 'Open alerts',
    noAlerts: 'No open alerts.',
    measurementsTitle: 'Measurements',
    submissionsTitle: 'Questionnaire submissions',
    alert: {
      rule: '{{type}}, version {{version}} · {{severity}}',
      condition: 'Condition: {{condition}}',
      questionnaireCondition: '“{{name}}” score in the {{bands}} band',
      or: ' or ',
      events: {
        created: 'Created',
        re_triggered: 'Re-triggered',
        seen: 'Seen',
        assigned: 'Assigned',
        closed: 'Closed',
        rule_changed: 'Rule changed',
        trigger_corrected: 'Triggering data corrected',
      },
      eventVersion: 'by version {{version}}',
    },
    ruleTypes: {
      threshold: 'Threshold rule',
      window: 'Time-window rule',
      questionnaire: 'Questionnaire rule',
      missing_data: 'Missing data',
    },
  },
}
