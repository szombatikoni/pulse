import { Button } from '@mantine/core'
import { type CSSProperties, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'

import { useCurrentUser } from '../../api/auth'
import { usePatientTasks } from '../../api/tasks'
import { StatusIcon } from '../../components/StatusLabel'
import { toLocalInput } from '../../format'
import i18n from '../../i18n'
import { MeasurementForm, type MeasurementPreset, type Message } from './MeasurementForm'
import { PlanNotices } from './PlanNotices'
import { TaskList } from './TaskList'
import './home.css'

/** A kérdőív oldaláról visszatérve a nyugta a router állapotában érkezik. */
export type HomeState = { notice?: Message } | null

function todayLabel(): string {
  const locale = i18n.language === 'en' ? 'en-GB' : 'hu-HU'
  return new Intl.DateTimeFormat(locale, { weekday: 'long', month: 'long', day: 'numeric' }).format(
    new Date(),
  )
}

function greetingKey(): string {
  const h = new Date().getHours()
  return h < 9
    ? 'home.patient.greetMorning'
    : h < 18
      ? 'home.patient.greetDay'
      : 'home.patient.greetEvening'
}

/** Fejléc: dátum, köszönés keresztnévvel, és hány mai teendőből hány kész. */
function Greeting({ patientId, name }: { patientId: string; name: string | null }) {
  const { t } = useTranslation()
  const tasks = usePatientTasks(patientId)
  // A magyar névsorrendben a keresztnév az utolsó szó („Tóth Mária” → Mária).
  const firstName = name?.trim().split(/\s+/).pop()
  const list = tasks.data ?? []
  const done = list.filter((x) => x.state === 'done').length
  return (
    <header className="pulse-ph">
      <span className="pulse-eyebrow">{todayLabel()}</span>
      <h1 className="pulse-display">
        {firstName ? t(greetingKey(), { name: firstName }) : t('home.patient.title')}
      </h1>
      {list.length > 0 && (
        <div className="pulse-progress">
          <div
            className="pulse-pbar"
            style={{ '--n': list.length } as CSSProperties}
            aria-hidden="true"
          >
            {list.map((x) => (
              <i key={`${x.kind}-${x.code}`} className={x.state === 'done' ? 'on' : undefined} />
            ))}
          </div>
          <span className="pulse-meta">
            {t('home.patient.progress', { count: list.length, done })}
          </span>
        </div>
      )}
    </header>
  )
}

/** A beteg kezdőoldala, a Teendőim (felületterv, 2026-10-30, 2. változat): csak a mai
 * teendők, fölöttük az előírások friss változásainak jelzése. A mérés rögzítése a teendő kártyáján nyílik ki, a kérdőív kitöltése saját
 * oldalon; mentés után a nyugta a lista alatt jelenik meg. A grafikonok és a mérési
 * napló az Előzményeim oldalon vannak. */
export function PatientHomePage() {
  const { t } = useTranslation()
  const me = useCurrentUser()
  const navigate = useNavigate()
  const location = useLocation()
  const patientId = me.data?.patient_id
  // Melyik teendő űrlapja nyitott: a teendő kódja, „free” (előírás nélküli mérés) vagy null.
  const [open, setOpen] = useState<{ code: string; preset: MeasurementPreset } | null>(null)
  const [notice, setNotice] = useState<Message | null>(
    () => (location.state as HomeState)?.notice ?? null,
  )

  if (!patientId) return null // a RequireAuth már betöltötte; betegnél mindig van

  const start = (code: string, preset: MeasurementPreset) => {
    setNotice(null)
    setOpen({ code, preset })
  }
  const form = (inTask: boolean) =>
    open && (
      <MeasurementForm
        key={`${open.code}-${open.preset.measuredAt ?? ''}`}
        patientId={patientId}
        preset={open.preset}
        inTask={inTask}
        onSaved={(_id, receipt) => {
          setOpen(null)
          setNotice(receipt)
        }}
        onClose={() => setOpen(null)}
      />
    )

  return (
    <div className="pulse-patient">
      <Greeting patientId={patientId} name={me.data?.name ?? null} />
      <PlanNotices patientId={patientId} />
      <TaskList
        patientId={patientId}
        renderForm={(task) =>
          task.kind === 'measurement' && open?.code === task.code ? form(true) : null
        }
        onRecord={(typeCode) => start(typeCode, { typeCode })}
        onCatchUp={(typeCode, at) =>
          start(typeCode, { typeCode, measuredAt: toLocalInput(new Date(at)), catchUp: true })
        }
        onFill={(code) => navigate(`/patient/questionnaires/${code}`)}
      />
      <div role="status">
        {notice && (
          <div className="pulse-receipt">
            <StatusIcon status={notice.ok ? 'ok' : 'severe'} size={22} />
            <div>
              <b>{notice.title}</b>
              {notice.text && <p className="pulse-hint">{notice.text}</p>}
            </div>
          </div>
        )}
      </div>
      {open?.code === 'free' ? (
        form(false)
      ) : (
        <div className="pulse-home-more">
          <Button variant="default" onClick={() => start('free', { typeCode: 'blood_pressure' })}>
            {t('measurements.freeTitle')}
          </Button>
          <Link className="pulse-linkbtn" to="/patient/history">
            {t('home.patient.historyLink')}
          </Link>
        </div>
      )}
    </div>
  )
}
