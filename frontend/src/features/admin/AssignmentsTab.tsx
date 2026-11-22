import { Button, NativeSelect } from '@mantine/core'
import { Link, LinkBreak } from '@phosphor-icons/react'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  type AdminAssignment,
  type AdminUser,
  useAdminAssignments,
  useCreateAssignment,
  useEndAssignment,
} from '../../api/admin'
import { DisabledMark } from '../../components/DisabledMark'
import { formatDateTime } from '../../format'
import { AdminErrorText, AdminModal } from './AdminUi'

// Érvényes az összerendelés, amíg nincs vége. A felület jövőbeli véget nem ad meg, így
// a szerver idejét nem kell a böngésző órájához mérni (óraeltérésnél félrevezetne).
const isOpen = (a: AdminAssignment) => a.valid_to === null

/** Összerendelések fül (felületterv): orvosonként egy kártya a betegei táblázatával
 * (Beteg, Érvényes), soronként csendes „Megszüntetés", kártyánként másodlagos „Új
 * összerendelés"; alul a megjegyzés, hogy a megszüntetés azonnal hat. A kezdet és a
 * vég mindig „most" (a hallgató döntése, 2026-11-16). */
export function AssignmentsTab({ users }: { users: AdminUser[] }) {
  const { t } = useTranslation()
  const assignments = useAdminAssignments()
  const end = useEndAssignment()
  const [adding, setAdding] = useState<AdminUser | null>(null)
  const doctors = users.filter((u) => u.role === 'doctor' && u.profile_id)
  // A letiltott betegek a soraikban „Letiltva" jelet kapnak (profil-azonosító szerint).
  const disabledPatients = new Set(
    users.filter((u) => u.role === 'patient' && !u.is_active).map((u) => u.profile_id),
  )

  if (assignments.isPending) return null
  if (assignments.isError) return <AdminErrorText error={assignments.error} />
  const rows = assignments.data

  return (
    <div className="ad-stack">
      {doctors.length === 0 && <p className="ad-note">{t('admin.assignments.noDoctors')}</p>}
      {doctors.map((doctor) => {
        const own = rows.filter((a) => a.doctor_id === doctor.profile_id)
        // Elöl az érvényesek, utánuk a megszüntetettek (a történet).
        const sorted = [...own.filter((a) => isOpen(a)), ...own.filter((a) => !isOpen(a))]
        const active = own.filter((a) => isOpen(a)).length
        return (
          <section
            key={doctor.id}
            className="pd-card ad-card"
            aria-label={doctor.name ?? doctor.email}
          >
            <div className="pd-card-head">
              <div className="left">
                <div className="head-line">
                  <h2 className="pd-h-card">{doctor.name}</h2>
                  {!doctor.is_active && <DisabledMark />}
                </div>
                <span className="pd-meta">
                  {t('admin.assignments.patientCount', { count: active })}
                </span>
              </div>
              <Button
                variant="default"
                size="xs"
                leftSection={<Link size={15} />}
                onClick={() => setAdding(doctor)}
                disabled={!doctor.is_active}
                aria-label={t('admin.assignments.addLabel', { doctor: doctor.name })}
              >
                {t('admin.assignments.add')}
              </Button>
            </div>
            {sorted.length === 0 ? (
              <p className="ad-note">{t('admin.assignments.empty')}</p>
            ) : (
              <div className="pd-tbl-wrap">
                <table className="pd-tbl">
                  <thead>
                    <tr>
                      <th>{t('admin.assignments.columns.patient')}</th>
                      <th>{t('admin.assignments.columns.valid')}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((a) => (
                      <tr key={a.id}>
                        <td className="strong">
                          {a.patient_name}
                          {disabledPatients.has(a.patient_id) && <DisabledMark />}
                        </td>
                        <td>
                          {isOpen(a)
                            ? t('admin.assignments.since', { from: formatDateTime(a.valid_from) })
                            : t('admin.assignments.between', {
                                from: formatDateTime(a.valid_from),
                                to: formatDateTime(a.valid_to!),
                              })}
                        </td>
                        <td className="n">
                          {isOpen(a) ? (
                            <Button
                              size="xs"
                              variant="subtle"
                              color="gray"
                              leftSection={<LinkBreak size={15} />}
                              loading={end.isPending && end.variables === a.id}
                              onClick={() => end.mutate(a.id)}
                              aria-label={t('admin.assignments.endLabel', {
                                patient: a.patient_name,
                                doctor: doctor.name,
                              })}
                            >
                              {t('admin.assignments.end')}
                            </Button>
                          ) : (
                            <span className="pd-muted">{t('admin.assignments.ended')}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {/* A megszüntetés hibája annál a kártyánál, amelyiken a sor van. */}
            {end.isError && own.some((a) => a.id === end.variables) && (
              <AdminErrorText error={end.error} />
            )}
          </section>
        )
      })}
      <p className="ad-note">{t('admin.assignments.note')}</p>
      {adding && (
        <AssignDialog
          key={adding.id}
          doctor={adding}
          users={users}
          assignments={rows}
          onClose={() => setAdding(null)}
        />
      )}
    </div>
  )
}

/** „Új összerendelés" ablak (a terv 5. része): az aktív betegek közül azok, akik
 * ennél az orvosnál éppen nincsenek hozzárendelve; a kezdet „most". */
function AssignDialog({
  doctor,
  users,
  assignments,
  onClose,
}: {
  doctor: AdminUser
  users: AdminUser[]
  assignments: AdminAssignment[]
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreateAssignment()
  const taken = new Set(
    assignments
      .filter((a) => a.doctor_id === doctor.profile_id && isOpen(a))
      .map((a) => a.patient_id),
  )
  const candidates = users
    .filter((u) => u.role === 'patient' && u.is_active && u.profile_id && !taken.has(u.profile_id))
    .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'hu'))
  const [patientId, setPatientId] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!patientId || !doctor.profile_id) return
    create.mutate({ doctor_id: doctor.profile_id, patient_id: patientId }, { onSuccess: onClose })
  }

  return (
    <AdminModal opened onClose={onClose} title={t('admin.assignments.dialogTitle')}>
      <form className="pd-modal-form" onSubmit={submit} noValidate>
        <div className="pd-modal-sum">
          <Link size={22} aria-hidden="true" />
          <div>
            <div className="t">{doctor.name}</div>
            <div className="pd-meta">{t('admin.assignments.hint')}</div>
          </div>
        </div>
        {candidates.length === 0 ? (
          <p className="ad-note">{t('admin.assignments.noCandidates')}</p>
        ) : (
          <NativeSelect
            label={t('admin.assignments.patient')}
            classNames={{ label: 'pd-field-label' }}
            data={[
              { value: '', label: t('admin.assignments.pick'), disabled: true },
              ...candidates.map((u) => ({ value: u.profile_id!, label: u.name ?? u.email })),
            ]}
            value={patientId}
            onChange={(e) => setPatientId(e.currentTarget.value)}
            data-autofocus
          />
        )}
        {create.isError && <AdminErrorText error={create.error} />}
        <div className="pd-modal-foot">
          <Button variant="subtle" color="gray" onClick={onClose}>
            {t('admin.cancel')}
          </Button>
          <Button type="submit" loading={create.isPending} disabled={!patientId}>
            {t('admin.assignments.submit')}
          </Button>
        </div>
      </form>
    </AdminModal>
  )
}
