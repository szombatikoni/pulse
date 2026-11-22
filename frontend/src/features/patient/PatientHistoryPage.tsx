import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useCurrentUser } from '../../api/auth'
import type { Measurement } from '../../api/measurements'
import { StatusIcon } from '../../components/StatusLabel'
import { MeasurementCharts } from '../doctor/charts/MeasurementCharts'
import '../doctor/patientDetail.css'
import { LatestValues } from './LatestValues'
import { MeasurementForm, type Message } from './MeasurementForm'
import { MeasurementHistory } from './MeasurementHistory'
import './home.css'

/** Előzményeim (felületterv, 2026-10-30, 2. változat): a legutóbbi értékek egy sorban,
 * alattuk ugyanazok a grafikonok, mint az orvos adatlapján (értékelés és határvonal
 * nélkül), legalul a napokra bontott mérési napló.
 *
 * A napló soraiból a mérés javítható (M3, A7): a rögzítő-űrlap a napló fölött nyílik
 * meg a mostani értékekkel, mentés után a nyugta ugyanott jelenik meg. */
export function PatientHistoryPage() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const patientId = me.data?.patient_id
  const [correcting, setCorrecting] = useState<Measurement | null>(null)
  const [notice, setNotice] = useState<Message | null>(null)
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
        {correcting && (
          <MeasurementForm
            key={correcting.id}
            patientId={patientId}
            correction={correcting}
            onSaved={(_id, receipt) => {
              setCorrecting(null)
              setNotice(receipt)
            }}
            onClose={() => setCorrecting(null)}
          />
        )}
        <div role="status">
          {notice && !correcting && (
            <div className="pulse-receipt">
              <StatusIcon status={notice.ok ? 'ok' : 'severe'} size={22} />
              <div>
                <b>{notice.title}</b>
                {notice.text && <p className="pulse-hint">{notice.text}</p>}
              </div>
            </div>
          )}
        </div>
        <MeasurementHistory
          patientId={patientId}
          onCorrect={(m) => {
            setNotice(null)
            setCorrecting(m)
          }}
        />
      </section>
    </div>
  )
}
