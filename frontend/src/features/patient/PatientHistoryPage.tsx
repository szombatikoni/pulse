import { useTranslation } from 'react-i18next'

import { useCurrentUser } from '../../api/auth'
import { MeasurementCharts } from '../doctor/charts/MeasurementCharts'
import '../doctor/patientDetail.css'
import { LatestValues } from './LatestValues'
import { MeasurementHistory } from './MeasurementHistory'
import './home.css'

/** Előzményeim (felületterv, 2026-10-30, 2. változat): a legutóbbi értékek egy sorban,
 * alattuk ugyanazok a grafikonok, mint az orvos adatlapján (értékelés és határvonal
 * nélkül), legalul a napokra bontott mérési napló. */
export function PatientHistoryPage() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const patientId = me.data?.patient_id
  if (!patientId) return null // a RequireAuth már betöltötte; betegnél mindig van

  return (
    <div className="pulse-patient pulse-history-page">
      <header className="pulse-ph">
        <h1 className="pulse-display">{t('home.patient.historyTitle')}</h1>
        <span className="pulse-meta">{t('home.patient.historyIntro')}</span>
      </header>
      <section className="pulse-sec" aria-labelledby="legutobbi-cim">
        <h2 className="pulse-h-sec" id="legutobbi-cim">
          {t('measurements.latestTitle')}
        </h2>
        <LatestValues patientId={patientId} />
      </section>
      <MeasurementCharts patientId={patientId} />
      <section className="pulse-sec" aria-labelledby="naplo-cim">
        <h2 className="pulse-h-sec" id="naplo-cim">
          {t('measurements.logTitle')}
        </h2>
        <MeasurementHistory patientId={patientId} />
      </section>
    </div>
  )
}
