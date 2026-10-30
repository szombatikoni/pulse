import { Button, Loader, Text, Title } from '@mantine/core'
import { ArrowRight, CaretRight, MagnifyingGlass, Users } from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { type PatientStatus, type PatientSummary, useDoctorPatients } from '../../api/patients'
import type { Task } from '../../api/tasks'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { ageInYears, formatRelative, formatSoon, formatTime } from '../../format'
import { reasonText, uniqueReasons } from './reasons'
import './patientList.css'

const STATUS_ORDER: PatientStatus[] = ['severe', 'attention', 'no_data', 'handled', 'ok']

// A lista négy csoportja (felületterv, 2026-10-30): ami orvosi döntést kér, külön
// kártyákon áll; a többi egy közös listában.
const GROUPS: { key: string; statuses: PatientStatus[]; loud?: boolean }[] = [
  { key: 'decide', statuses: ['severe', 'attention'], loud: true },
  { key: 'watch', statuses: ['no_data'] },
  { key: 'handled', statuses: ['handled'] },
  { key: 'ok', statuses: ['ok'] },
]

/** Sürgősség szerint: előbb a státusz, azon belül a frissebb adat. */
const byUrgency = (a: PatientSummary, b: PatientSummary) =>
  STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
  (b.last_data_at ?? '').localeCompare(a.last_data_at ?? '')

type TaskTone = 'ok' | 'due' | 'late' | 'none'

/** A teendők egy sorban: előbb ami lejárt vagy elmaradt, aztán a ma esedékes;
 * ha egyik sincs, „a teendők rendben". */
function taskSummary(t: TFunction, tasks: Task[]): { tone: TaskTone; text: string } {
  if (tasks.length === 0) return { tone: 'none', text: '—' }
  const name = (task: Task) =>
    task.kind === 'measurement' ? t(`measurementTypes.${task.code}`) : task.name
  const late = tasks.filter((x) => x.state === 'late')
  const missed = tasks.filter((x) => x.state !== 'late' && x.previous_missed)
  const today = new Date().toDateString()
  const dueToday = tasks.filter(
    (x) => x.state === 'due' && new Date(x.due_at).toDateString() === today,
  )
  const problems = late.length + missed.length
  const more = problems > 1 ? ` ${t('doctor.tasks.more', { count: problems - 1 })}` : ''
  if (late.length)
    return { tone: 'late', text: t('doctor.tasks.late', { name: name(late[0]) }) + more }
  if (missed.length)
    return { tone: 'late', text: t('doctor.tasks.missed', { name: name(missed[0]) }) + more }
  if (dueToday.length)
    return {
      tone: 'due',
      text: t('doctor.tasks.dueToday', {
        name: name(dueToday[0]),
        when: formatSoon(t, dueToday[0].due_at),
      }),
    }
  return { tone: 'ok', text: t('doctor.tasks.onTrack') }
}

/** Szűrőcsempék: státuszonként a darabszám; a nullás csempe halvány és nem kattintható. */
function StatusTiles({
  patients,
  value,
  onChange,
}: {
  patients: PatientSummary[]
  value: PatientStatus | 'all'
  onChange: (value: PatientStatus | 'all') => void
}) {
  const { t } = useTranslation()
  const tile = (key: PatientStatus | 'all', count: number, label: string, glyph: ReactNode) => (
    <button
      key={key}
      type="button"
      className={count ? 'pl-tile' : 'pl-tile zero'}
      aria-pressed={value === key}
      aria-disabled={count === 0 || undefined}
      onClick={() => count && onChange(value === key ? 'all' : key)}
    >
      {glyph}
      <span className="pl-tile-n">{count}</span>
      <span className="pl-tile-l">{label}</span>
    </button>
  )
  return (
    <div className="pl-tiles" role="group" aria-label={t('doctor.filterLabel')}>
      {tile(
        'all',
        patients.length,
        t('doctor.filterAll'),
        <span className="pl-tile-all" aria-hidden="true">
          <Users size={15} weight="bold" />
        </span>,
      )}
      {STATUS_ORDER.map((status) =>
        tile(
          status,
          patients.filter((p) => p.status === status).length,
          t(`status.${status}`),
          <StatusIcon status={status} size={26} />,
        ),
      )}
    </div>
  )
}

/** Egy beteg sora: az egész sor link az adatlapra; a státuszcímke az első szöveg. */
function PatientRow({ p, loud }: { p: PatientSummary; loud?: boolean }) {
  const { t } = useTranslation()
  const [primary, ...others] = uniqueReasons(p.reasons)
  const tasks = taskSummary(t, p.tasks ?? [])
  return (
    <Link
      to={`/doctor/patients/${p.id}`}
      className={loud ? 'pulse-prow pl-row pl-cols loud' : 'pulse-prow pl-row pl-cols'}
      data-s={p.status}
    >
      <span className="c-status">
        <StatusLabel status={p.status} />
      </span>
      <span className="c-name">
        <span className="pl-name">{p.name}</span>
        <span className="pl-age">{t('doctor.age', { age: ageInYears(p.birth_date) })}</span>
      </span>
      <span className="c-reason">
        <span className={p.status === 'ok' ? 'pl-r-main calm' : 'pl-r-main'}>
          {reasonText(t, primary)}
        </span>
        {others.map((r, i) => (
          <span key={i} className="pl-r-sub">
            <StatusIcon status={r.status} size={16} />
            <span>{reasonText(t, r)}</span>
          </span>
        ))}
      </span>
      <span className={tasks.tone === 'late' ? 'c-tasks late' : 'c-tasks'}>{tasks.text}</span>
      <span className="c-fresh">
        {p.last_data_at ? formatRelative(t, p.last_data_at) : t('doctor.noData')}
      </span>
      <span className="c-chev" aria-hidden="true">
        <CaretRight size={16} weight="bold" />
      </span>
    </Link>
  )
}

/** Az orvos priorizált beteglistája (F9), felületterv 2026-10-30: csoportok
 * (Döntésre vár, Figyelendő, Kezelés alatt, Rendben), szűrőcsempék, keresés. */
export function DoctorPatientsPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const patients = useDoctorPatients()
  const [filter, setFilter] = useState<PatientStatus | 'all'>('all')
  const [query, setQuery] = useState('')

  if (patients.isPending) return <Loader />
  if (patients.isError) return <Text c="red">{t('errors.unavailable')}</Text>

  const all = patients.data
  const q = query.trim().toLocaleLowerCase('hu')
  const visible = all.filter(
    (p) =>
      (filter === 'all' || p.status === filter) &&
      (!q || p.name.toLocaleLowerCase('hu').includes(q)),
  )
  const decide = all.filter((p) => p.status === 'severe' || p.status === 'attention')
  const urgent = [...decide].sort(byUrgency)[0]
  const today = new Date().toLocaleDateString(i18n.language, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  return (
    <div className="pl-page">
      <header className="pl-ph">
        <div className="pl-ph-text">
          <span className="pl-eyebrow">{today}</span>
          <Title order={1} className="pl-title">
            {t('home.doctor.title')}
          </Title>
          <div className="pl-ph-meta">
            <span>{t('doctor.list.count', { count: all.length })}</span>
            <span>{t('doctor.list.decide', { count: decide.length })}</span>
            <span>
              {t('doctor.list.updated', { time: formatTime(new Date(patients.dataUpdatedAt)) })}
            </span>
          </div>
        </div>
        {all.length > 0 && (
          <div className="pl-ph-actions">
            <label className="pl-search">
              <MagnifyingGlass size={16} aria-hidden="true" />
              <input
                type="search"
                className="pl-input"
                aria-label={t('doctor.search')}
                placeholder={t('doctor.search')}
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.currentTarget.value)}
              />
            </label>
            {urgent && (
              // Gomb, nem link: a beteg nevére szóló link a listában egyedi marad.
              <Button
                onClick={() => navigate(`/doctor/patients/${urgent.id}`)}
                rightSection={<ArrowRight size={16} weight="bold" />}
              >
                {t('doctor.list.urgent', { name: urgent.name })}
              </Button>
            )}
          </div>
        )}
      </header>

      {all.length === 0 ? (
        <Text c="dimmed">{t('doctor.empty')}</Text>
      ) : (
        <>
          <StatusTiles patients={all} value={filter} onChange={setFilter} />
          <div className="pl-stack">
            <div className="pl-cols pl-cols-head" aria-hidden="true">
              <span>{t('doctor.columns.status')}</span>
              <span>{t('doctor.columns.patient')}</span>
              <span>{t('doctor.columns.reason')}</span>
              <span>{t('doctor.columns.tasks')}</span>
              <span className="r">{t('doctor.columns.lastData')}</span>
              <span />
            </div>
            {GROUPS.map((g) => {
              const list = visible.filter((p) => g.statuses.includes(p.status)).sort(byUrgency)
              if (!list.length) return null
              const title = t(`doctor.list.groups.${g.key}`)
              return (
                <section key={g.key} className="pl-group" aria-label={title}>
                  <div className="pl-group-head">
                    <h2>{title}</h2>
                    <span className="pl-group-n">{list.length}</span>
                  </div>
                  <div className={g.loud ? 'pl-loud' : 'pl-plist'}>
                    {list.map((p) => (
                      <PatientRow key={p.id} p={p} loud={g.loud} />
                    ))}
                  </div>
                </section>
              )
            })}
            {visible.length === 0 && <p className="pl-no-match">{t('doctor.noMatch')}</p>}
          </div>
        </>
      )}
    </div>
  )
}
