import { ActionIcon, Button, CopyButton, Loader } from '@mantine/core'
import {
  CaretRight,
  Check,
  Copy,
  LinkBreak,
  Minus,
  NotEquals,
  Warning,
  X,
} from '@phosphor-icons/react'
import type { TFunction } from 'i18next'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { type NiceEvaluation, type NiceResult, useNiceEvaluation } from '../../api/nice'
import { formatDate, formatNumber, todayInput, unitLabel, formatRelative } from '../../format'
import i18n from '../../i18n'

const locale = () => (i18n.language === 'en' ? 'en-GB' : 'hu-HU')

/** Az átlag alapból egy tizedesre. Ha a kerekített érték éppen a célérték
 * (135,0), két tizedes, hogy a „135,0, mégsem teljesül” ne tűnjön hibának. */
function formatMean(value: number, target: number | null): string {
  const digits = target !== null && Math.round(value * 10) / 10 === target ? 2 : 1
  return new Intl.NumberFormat(locale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

/** Teljes pontosság a Részletekhez (a JavaScript legrövidebb pontos alakja),
 * magyarul tizedesvesszővel: 137,66666666666666. */
const formatFull = (value: number) =>
  i18n.language === 'en' ? String(value) : String(value).replace('.', ',')

/** Az időszak vége nyitott (a mai nap éjfele): az utolsó beszámított nap az előtte lévő. */
function lastDay(endIso: string): string {
  const [y, m, d] = endIso.slice(0, 10).split('-').map(Number)
  return todayInput(new Date(y, m - 1, d - 1))
}

const num = (value: unknown): number | null => (typeof value === 'number' ? value : null)

/** Az 503 cql_unavailable a kiértékelő szolgáltatás kiesése (D7a). */
function isCqlUnavailable(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 503) return false
  const detail = error.detail as { code?: unknown } | null
  return detail?.code === 'cql_unavailable'
}

function errorText(t: TFunction, error: unknown): string {
  if (isCqlUnavailable(error)) return t('doctor.nice.unavailable')
  const forbidden = error instanceof ApiError && error.status === 403
  return t(forbidden ? 'errors.forbidden' : 'errors.unavailable')
}

/** Az ítélet: semleges, szögletes, körvonalas címke jellel és szóval. Szándékosan
 * nem a beteg-státusz teli, kerek, színes címkéje (StatusLabel). */
function Verdict({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="pd-nice-verdict">
      <span className="g" aria-hidden="true">
        {icon}
      </span>
      {children}
    </span>
  )
}

/** Egy mező értéke a Részletek táblázatában (a nem alapsoroknál, eltéréskor). */
function fieldValue(t: TFunction, field: keyof NiceResult, r: NiceResult): string {
  const value = r[field]
  if (value === null) return t('doctor.nice.none')
  if (typeof value === 'boolean')
    return t(value ? 'doctor.nice.details.yes' : 'doctor.nice.details.no')
  if (typeof value === 'number') return formatFull(value)
  if (Array.isArray(value)) {
    return field === 'included_days' ? value.map(formatDate).join(', ') : String(value.length)
  }
  return formatDate(value)
}

type Row = { key: string; label: string; cql: string; own: string; fields: (keyof NiceResult)[] }

/** A két számítás mezőnként: az alapsorok, és ha egy eltérő mezőnek nincs
 * alapsora (pl. életkor), arra egy külön sor, hogy az eltérés is látsszon. */
function comparisonRows(t: TFunction, e: NiceEvaluation): Row[] {
  const mean = (v: number | null) => (v === null ? t('doctor.nice.none') : formatFull(v))
  const days = (r: NiceResult) =>
    `${r.included_day_count ?? t('doctor.nice.none')} / ${r.included_reading_ids.length}`
  const met = (r: NiceResult) =>
    r.target_met === null
      ? t('doctor.nice.notAssessable')
      : t(r.target_met ? 'doctor.nice.details.yes' : 'doctor.nice.details.no')
  const rows: Row[] = [
    {
      key: 'sys',
      label: t('doctor.nice.details.meanSystolic'),
      cql: mean(e.cql.mean_systolic),
      own: mean(e.own.mean_systolic),
      fields: ['mean_systolic'],
    },
    {
      key: 'dia',
      label: t('doctor.nice.details.meanDiastolic'),
      cql: mean(e.cql.mean_diastolic),
      own: mean(e.own.mean_diastolic),
      fields: ['mean_diastolic'],
    },
    {
      key: 'days',
      label: t('doctor.nice.details.daysReadings'),
      cql: days(e.cql),
      own: days(e.own),
      fields: ['included_day_count', 'included_reading_ids', 'included_days'],
    },
    {
      key: 'met',
      label: t('doctor.nice.details.targetMet'),
      cql: met(e.cql),
      own: met(e.own),
      fields: ['target_met', 'enough_data'],
    },
  ]
  const covered = new Set(rows.flatMap((row) => row.fields))
  for (const field of e.mismatched_fields.filter((f) => !covered.has(f))) {
    const name = t(`doctor.nice.fields.${field}`)
    rows.push({
      key: field,
      label: name.charAt(0).toUpperCase() + name.slice(1),
      cql: fieldValue(t, field, e.cql),
      own: fieldValue(t, field, e.own),
      fields: [field],
    })
  }
  return rows
}

/** Az alkalmazott paraméterek egy mondatban, a válasz paramétereiből. */
function parameterText(t: TFunction, p: Record<string, unknown>): string {
  const parts: string[] = []
  if (typeof p['Exclude First Day'] === 'boolean') {
    parts.push(
      t(
        p['Exclude First Day']
          ? 'doctor.nice.details.excludeFirst'
          : 'doctor.nice.details.includeFirst',
      ),
    )
  }
  const minDays = num(p['Min Included Days'])
  if (minDays !== null) parts.push(t('doctor.nice.details.minDays', { count: minDays }))
  const age = num(p['Age Threshold Years'])
  if (age !== null) parts.push(t('doctor.nice.details.ageLimit', { age }))
  const sys = num(p['Target Systolic Below Age Threshold'])
  const dia = num(p['Target Diastolic Below Age Threshold'])
  const sysOld = num(p['Target Systolic At Or Above Age Threshold'])
  const diaOld = num(p['Target Diastolic At Or Above Age Threshold'])
  if (age !== null && sys !== null && dia !== null && sysOld !== null && diaOld !== null) {
    parts.push(
      t('doctor.nice.details.targets', {
        sys: formatNumber(sys),
        dia: formatNumber(dia),
        age,
        sysOld: formatNumber(sysOld),
        diaOld: formatNumber(diaOld),
      }),
    )
  }
  if (p['Both Components Must Be Below Target'] === true) {
    parts.push(t('doctor.nice.details.bothBelow'))
  }
  return parts.join('; ')
}

function Details({ evaluation }: { evaluation: NiceEvaluation }) {
  const { t } = useTranslation()
  const different = new Set(evaluation.mismatched_fields)
  const { library, engine } = evaluation
  const sha = library.sha256 ?? ''
  const engineText = Object.entries(engine)
    .map(([name, version]) => `${name === 'node' ? 'Node' : name} ${version}`)
    .join(', ')
  return (
    // Eltérésnél magától nyitva (a panel minden futásnál újra felépül, lásd a key-t).
    <details className="pd-events pd-nice-det" open={!evaluation.matches}>
      <summary>
        <CaretRight size={14} weight="bold" />
        {t('doctor.nice.details.title')}
      </summary>
      <div className="pd-nice-det-body">
        <table className="pd-nice-cmp">
          <thead>
            <tr>
              <td />
              <th scope="col">{t('doctor.nice.details.cql')}</th>
              <th scope="col">{t('doctor.nice.details.own')}</th>
            </tr>
          </thead>
          <tbody>
            {comparisonRows(t, evaluation).map((row) => {
              const diff = row.fields.some((f) => different.has(f))
              return (
                <tr key={row.key} className={diff ? 'diff' : undefined}>
                  <th scope="row">
                    {diff && <NotEquals size={12} weight="bold" aria-hidden="true" />}
                    {row.label}
                  </th>
                  <td>{row.cql}</td>
                  <td>{row.own}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <dl className="pd-nice-kv">
          <dt>{t('doctor.nice.details.library')}</dt>
          <dd>
            {library.id} {library.version}
          </dd>
          {sha && (
            <>
              <dt>{t('doctor.nice.details.sha')}</dt>
              <dd className="pd-nice-sha">
                <span className="mono" title={sha}>
                  {`${sha.slice(0, 8)}…${sha.slice(-4)}`}
                </span>
                <CopyButton value={sha}>
                  {({ copied, copy }) => (
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      size="sm"
                      onClick={copy}
                      aria-label={t(
                        copied ? 'doctor.nice.details.copied' : 'doctor.nice.details.copy',
                      )}
                      title={t(copied ? 'doctor.nice.details.copied' : 'doctor.nice.details.copy')}
                    >
                      {copied ? <Check size={13} /> : <Copy size={13} />}
                    </ActionIcon>
                  )}
                </CopyButton>
              </dd>
            </>
          )}
          <dt>{t('doctor.nice.details.engine')}</dt>
          <dd>{engineText}</dd>
          {evaluation.duration_ms !== null && (
            <>
              <dt>{t('doctor.nice.details.duration')}</dt>
              <dd>
                {t('doctor.nice.details.durationValue', {
                  ms: Math.round(evaluation.duration_ms),
                })}
              </dd>
            </>
          )}
          <dt>{t('doctor.nice.details.parameters')}</dt>
          <dd>{parameterText(t, evaluation.parameters)}</dd>
        </dl>
      </div>
    </details>
  )
}

/** Az eredmény: alapból a CQL-motoré, a saját számítás a Részletekben. */
function Result({ evaluation }: { evaluation: NiceEvaluation }) {
  const { t } = useTranslation()
  const r = evaluation.cql
  const p = evaluation.parameters
  const mismatch = !evaluation.matches
  const showMean = r.enough_data === true && r.mean_systolic !== null && r.mean_diastolic !== null
  const notAssessable = !mismatch && r.target_met === null
  const showTarget = !notAssessable && r.target_systolic !== null && r.target_diastolic !== null
  const ageLimit = num(p['Age Threshold Years'])
  const minDays = num(p['Min Included Days']) ?? 3
  const noReadings = r.included_reading_ids.length === 0 && r.excluded_reading_ids.length === 0

  let verdict: ReactNode
  if (mismatch) {
    verdict = (
      <Verdict icon={<NotEquals size={12} weight="bold" />}>{t('doctor.nice.mismatch')}</Verdict>
    )
  } else if (r.target_met === null) {
    verdict = (
      <Verdict icon={<Minus size={12} weight="bold" />}>{t('doctor.nice.notAssessable')}</Verdict>
    )
  } else if (r.target_met) {
    verdict = <Verdict icon={<Check size={12} weight="bold" />}>{t('doctor.nice.met')}</Verdict>
  } else {
    verdict = <Verdict icon={<X size={12} weight="bold" />}>{t('doctor.nice.notMet')}</Verdict>
  }

  return (
    <div className="pd-nice-result">
      {showMean && (
        <div>
          <div className="pd-nice-val">
            <span className="v">
              {formatMean(r.mean_systolic!, r.target_systolic)} /{' '}
              {formatMean(r.mean_diastolic!, r.target_diastolic)}
            </span>
            <span className="u">{unitLabel(t, 'mm[Hg]')}</span>
          </div>
          {/* Eltérésnél a kiemelt szám csak az egyik számítás (a CQL-motor) értéke. */}
          <div className="pd-nice-val-sub">
            {t(mismatch ? 'doctor.nice.meanCql' : 'doctor.nice.mean')}
          </div>
        </div>
      )}
      <div className="pd-nice-verdict-row">
        {verdict}
        {showTarget && (
          <span className="pd-nice-target">
            {t('doctor.nice.target', {
              sys: formatNumber(r.target_systolic!),
              dia: formatNumber(r.target_diastolic!),
            })}
          </span>
        )}
      </div>
      {notAssessable && (
        <p className="pd-nice-text">
          {noReadings
            ? t('doctor.nice.noReadings')
            : t('doctor.nice.tooFewDays', { count: r.included_day_count ?? 0, min: minDays })}
        </p>
      )}
      {mismatch && (
        <div className="pd-nice-notice strong" role="alert">
          <Warning size={18} aria-hidden="true" />
          <span>
            {t('doctor.nice.mismatchText', {
              fields: evaluation.mismatched_fields
                .map((f) => t(`doctor.nice.fields.${f}`))
                .join(', '),
            })}
          </span>
        </div>
      )}
      <dl className="pd-nice-facts">
        <dt>{t('doctor.nice.period')}</dt>
        <dd>
          {t('doctor.nice.periodValue', {
            from: formatDate(evaluation.period.start),
            to: formatDate(lastDay(evaluation.period.end)),
          })}
        </dd>
        <dt>{t('doctor.nice.excluded')}</dt>
        <dd>
          {r.excluded_first_day ? (
            <>
              {formatDate(r.excluded_first_day)}{' '}
              <span className="pd-muted">
                {t('doctor.nice.excludedCount', { count: r.excluded_reading_ids.length })}
              </span>
            </>
          ) : (
            t('doctor.nice.none')
          )}
        </dd>
        <dt>{t('doctor.nice.included')}</dt>
        <dd>
          {t('doctor.nice.includedValue', {
            days: t('doctor.nice.includedDays', { count: r.included_day_count ?? 0 }),
            count: r.included_reading_ids.length,
          })}
        </dd>
        {r.age_in_years !== null && (
          <>
            <dt>{t('doctor.nice.age')}</dt>
            <dd>
              {t('doctor.nice.ageValue', { age: r.age_in_years })}
              {ageLimit !== null && (
                <>
                  {' '}
                  <span className="pd-muted">
                    {t(
                      r.age_in_years < ageLimit
                        ? 'doctor.nice.ageBelow'
                        : 'doctor.nice.ageAtOrAbove',
                      { limit: ageLimit },
                    )}
                  </span>
                </>
              )}
            </dd>
          </>
        )}
      </dl>
      {!mismatch && (
        <p className="pd-nice-agree">
          <Check size={15} aria-hidden="true" />
          {t('doctor.nice.agree')}
        </p>
      )}
      <Details evaluation={evaluation} />
    </div>
  )
}

/** NICE NG136 szerinti otthoni vérnyomásátlag az orvos adatlapján (M3, K2, 3.
 * lépés). Gombra fut (useMutation): az eredmény nem tárolódik, csak a komponens
 * állapotában él; új futáskor (és hibánál) az előző eltűnik, hogy ne lehessen
 * frissnek hinni. Státuszt és riasztást nem érint. */
export function NicePanel({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const nice = useNiceEvaluation(patientId)
  const run = () => nice.mutate()

  let button: ReactNode
  if (nice.isPending) {
    button = (
      <Button size="xs" disabled leftSection={<Loader size={12} color="gray" />}>
        {t('doctor.nice.running')}
      </Button>
    )
  } else if (nice.isSuccess) {
    button = (
      <Button size="xs" variant="subtle" color="gray" onClick={run}>
        {t('doctor.nice.rerun')}
      </Button>
    )
  } else {
    button = (
      <Button size="xs" onClick={run}>
        {t(nice.isError ? 'doctor.nice.retry' : 'doctor.nice.run')}
      </Button>
    )
  }

  return (
    <section className="pd-card pd-nice" aria-labelledby="pd-h-nice">
      <div className="pd-card-head">
        <div className="left">
          <h2 className="pd-h-card" id="pd-h-nice">
            {t('doctor.nice.title')}
          </h2>
          <span className="pd-meta">
            {nice.isSuccess
              ? t('doctor.nice.evaluatedAt', {
                  when: formatRelative(t, nice.data.evaluation_time),
                })
              : t('doctor.nice.meta')}
          </span>
        </div>
        {button}
      </div>
      <div aria-live="polite">
        {nice.isSuccess ? (
          <Result key={nice.data.evaluation_time} evaluation={nice.data} />
        ) : nice.isError ? (
          <div className="pd-nice-notice">
            <LinkBreak size={18} aria-hidden="true" />
            <span>{errorText(t, nice.error)}</span>
          </div>
        ) : (
          <div className="pd-nice-intro">
            <p>{t('doctor.nice.intro')}</p>
            <p className="pd-muted">{t('doctor.nice.noEffect')}</p>
          </div>
        )}
      </div>
      <p className="pd-nice-disc">{t('doctor.nice.disclaimer')}</p>
    </section>
  )
}
