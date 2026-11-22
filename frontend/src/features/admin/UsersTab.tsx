import { Button, TextInput, VisuallyHidden } from '@mantine/core'
import type { TFunction } from 'i18next'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { type AdminUser, useCreateUser, useRenameUser, useSetUserActive } from '../../api/admin'
import type { Role } from '../../api/auth'
import { formatRelative, todayInput } from '../../format'
import { ActiveBand, AdminErrorText, AdminModal } from './AdminUi'

// A szerver szabályai (backend/app/services/admin.py, core/security.py): a felület
// ugyanezekkel előre ellenőriz, a végső döntés a szerveré.
const PASSWORD_MIN = 10
const PASSWORD_MAX = 255
const NAME_MAX = 200
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const ROLES: Role[] = ['patient', 'doctor', 'admin']

/** A felhasználó neve a táblázatban; az adminnak nincs neve, ott a szerepköre. */
function displayName(t: TFunction, user: AdminUser): string {
  return user.name ?? t('roles.admin')
}

/** Felhasználók fül (felületterv): Név, E-mail-cím, Szerepkör, Állapot, Utolsó
 * belépés, soronként „Szerkesztés". */
export function UsersTab({ users, meId }: { users: AdminUser[]; meId?: string }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState<AdminUser | null>(null)
  // A szerkesztett felhasználó friss adata (a mentés után a lista újratöltődik).
  const current = editing ? (users.find((u) => u.id === editing.id) ?? editing) : null

  return (
    <div className="pd-card ad-card">
      <div className="pd-tbl-wrap">
        <table className="pd-tbl">
          <thead>
            <tr>
              <th>{t('admin.users.columns.name')}</th>
              <th>{t('admin.users.columns.email')}</th>
              <th>{t('admin.users.columns.role')}</th>
              <th>{t('admin.users.columns.state')}</th>
              <th>{t('admin.users.columns.lastLogin')}</th>
              <th>
                <VisuallyHidden>{t('admin.users.edit')}</VisuallyHidden>
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td className="strong">{displayName(t, user)}</td>
                <td>{user.email}</td>
                <td>{t(`roles.${user.role}`)}</td>
                <td>
                  <ActiveBand active={user.is_active} />
                </td>
                <td className="nowrap">
                  {user.last_login_at
                    ? formatRelative(t, user.last_login_at)
                    : t('admin.users.neverLoggedIn')}
                </td>
                <td className="n">
                  <Button
                    size="xs"
                    variant="subtle"
                    color="gray"
                    onClick={() => setEditing(user)}
                    aria-label={t('admin.users.editLabel', { name: displayName(t, user) })}
                  >
                    {t('admin.users.edit')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {current && (
        <EditUserDialog
          key={current.id}
          user={current}
          isMe={current.id === meId}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

type Draft = { role: Role; email: string; name: string; birthDate: string; password: string }
const EMPTY: Draft = { role: 'patient', email: '', name: '', birthDate: '', password: '' }

/** A kliensoldali ellenőrzés: mezőnként az első hiba kódja (a szerver kódjaival). */
function validate(d: Draft): Partial<Record<keyof Draft, string>> {
  const errors: Partial<Record<keyof Draft, string>> = {}
  if (!EMAIL_PATTERN.test(d.email.trim())) errors.email = 'email_invalid'
  if (d.role !== 'admin') {
    if (!d.name.trim()) errors.name = 'name_required'
    else if (d.name.trim().length > NAME_MAX) errors.name = 'name_too_long'
  }
  if (d.role === 'patient') {
    if (!d.birthDate) errors.birthDate = 'birth_date_required'
    else if (d.birthDate < '1900-01-01' || d.birthDate > todayInput())
      errors.birthDate = 'birth_date_invalid'
  }
  if (d.password.length < PASSWORD_MIN || d.password.length > PASSWORD_MAX)
    errors.password = 'password_length'
  return errors
}

/** „Új felhasználó" ablak (a terv 5. része): szerepkör, e-mail-cím, név (adminnál
 * nincs), születési dátum (csak betegnél), kezdeti jelszó; Mégse / Létrehozás. */
export function CreateUserDialog({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const create = useCreateUser()
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [shown, setShown] = useState(false)
  const errors = validate(draft)
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const error = (key: keyof Draft) =>
    shown && errors[key] ? t(`admin.errors.${errors[key]}`) : undefined

  const close = () => {
    setDraft(EMPTY)
    setShown(false)
    create.reset()
    onClose()
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setShown(true)
    if (Object.keys(errors).length) return
    create.mutate(
      {
        email: draft.email.trim(),
        password: draft.password,
        role: draft.role,
        ...(draft.role !== 'admin' ? { name: draft.name.trim() } : {}),
        ...(draft.role === 'patient' ? { birth_date: draft.birthDate } : {}),
      },
      { onSuccess: close },
    )
  }

  return (
    <AdminModal opened={opened} onClose={close} title={t('admin.create.title')}>
      <form className="pd-modal-form" onSubmit={submit} noValidate>
        <div className="pd-field">
          <span className="pd-field-label" id="ad-new-role">
            {t('admin.create.role')}
          </span>
          <div className="pd-seg" role="group" aria-labelledby="ad-new-role">
            {ROLES.map((role) => (
              <button
                key={role}
                type="button"
                aria-pressed={draft.role === role}
                onClick={() => set({ role })}
              >
                {t(`roles.${role}`)}
              </button>
            ))}
          </div>
        </div>
        <TextInput
          label={t('admin.create.email')}
          classNames={{ label: 'pd-field-label' }}
          type="email"
          autoComplete="off"
          value={draft.email}
          onChange={(e) => set({ email: e.currentTarget.value })}
          error={error('email')}
          required
          data-autofocus
        />
        {draft.role !== 'admin' && (
          <TextInput
            label={t('admin.create.name')}
            classNames={{ label: 'pd-field-label' }}
            value={draft.name}
            maxLength={NAME_MAX}
            onChange={(e) => set({ name: e.currentTarget.value })}
            error={error('name')}
            required
          />
        )}
        {draft.role === 'patient' && (
          <TextInput
            type="date"
            label={t('admin.create.birthDate')}
            description={t('admin.create.birthDateHint')}
            classNames={{ label: 'pd-field-label', description: 'pd-hint' }}
            value={draft.birthDate}
            min="1900-01-01"
            max={todayInput()}
            onChange={(e) => set({ birthDate: e.currentTarget.value })}
            error={error('birthDate')}
            required
          />
        )}
        <TextInput
          label={t('admin.create.password')}
          // A tipp és a hibaüzenet közül egyszerre csak az egyik látszik.
          description={error('password') ? undefined : t('admin.create.passwordHint')}
          classNames={{ label: 'pd-field-label', description: 'pd-hint' }}
          inputWrapperOrder={['label', 'input', 'description', 'error']}
          autoComplete="new-password"
          value={draft.password}
          maxLength={PASSWORD_MAX}
          onChange={(e) => set({ password: e.currentTarget.value })}
          error={error('password')}
          required
        />
        {create.isError && <AdminErrorText error={create.error} />}
        <div className="pd-modal-foot">
          <Button variant="subtle" color="gray" onClick={close}>
            {t('admin.cancel')}
          </Button>
          <Button type="submit" loading={create.isPending}>
            {t('admin.create.submit')}
          </Button>
        </div>
      </form>
    </AdminModal>
  )
}

/** „Szerkesztés" ablak (a terv 5. része): a név javítása, és a fiók letiltása vagy
 * visszaengedélyezése; a letiltás külön megerősítő lépés. A saját fiók nem tiltható le. Az e-mail-cím és a
 * szerepkör létrehozás után nem változik (a hallgató döntése, 2026-11-16). */
function EditUserDialog({
  user,
  isMe,
  onClose,
}: {
  user: AdminUser
  isMe: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const rename = useRenameUser()
  const setActive = useSetUserActive()
  const [name, setName] = useState(user.name ?? '')
  const [shown, setShown] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const trimmed = name.trim()
  const nameError = !trimmed ? 'name_required' : trimmed.length > NAME_MAX ? 'name_too_long' : null

  const save = (e: FormEvent) => {
    e.preventDefault()
    setShown(true)
    if (nameError) return
    rename.mutate({ id: user.id, name: trimmed }, { onSuccess: onClose })
  }

  const toggle = (active: boolean) =>
    setActive.mutate({ id: user.id, active }, { onSuccess: () => setConfirming(false) })

  return (
    <AdminModal opened onClose={onClose} title={displayName(t, user)}>
      <div className="pd-modal-form">
        <div className="pd-modal-sum">
          <ActiveBand active={user.is_active} />
          <div>
            <div className="t">{user.email}</div>
            <div className="pd-meta">
              {t(`roles.${user.role}`)} · {t('admin.edit.fixed')}
            </div>
          </div>
        </div>

        {/* A letiltás megerősítése külön lépés: közben csak az látszik. */}
        {!confirming && user.name !== null && (
          <form className="pd-modal-form" onSubmit={save} noValidate>
            <TextInput
              label={t('admin.edit.name')}
              classNames={{ label: 'pd-field-label' }}
              value={name}
              maxLength={NAME_MAX}
              onChange={(e) => setName(e.currentTarget.value)}
              error={shown && nameError ? t(`admin.errors.${nameError}`) : undefined}
              required
              data-autofocus
            />
            {rename.isError && <AdminErrorText error={rename.error} />}
            <div className="pd-modal-foot">
              <Button variant="subtle" color="gray" onClick={onClose}>
                {t('admin.cancel')}
              </Button>
              <Button type="submit" loading={rename.isPending} disabled={trimmed === user.name}>
                {t('admin.edit.save')}
              </Button>
            </div>
          </form>
        )}

        {confirming ? (
          <div className="ad-confirm" role="group" aria-labelledby="ad-confirm-title">
            <h3 className="pd-h-card" id="ad-confirm-title">
              {t('admin.edit.disable')}
            </h3>
            <span>
              {t(user.role === 'patient' ? 'admin.edit.confirmPatient' : 'admin.edit.confirm')}
            </span>
            {setActive.isError && <AdminErrorText error={setActive.error} />}
            <div className="pd-modal-foot">
              <Button variant="subtle" color="gray" onClick={() => setConfirming(false)}>
                {t('admin.edit.back')}
              </Button>
              {/* A megerősítő lépés fő gombja, mint az előírás visszavonásánál (CarePlan). */}
              <Button onClick={() => toggle(false)} loading={setActive.isPending}>
                {t('admin.edit.confirmYes')}
              </Button>
            </div>
          </div>
        ) : (
          <section className="ad-section" aria-labelledby="ad-account-state">
            <div className="ad-section-row">
              <h3 className="pd-h-card" id="ad-account-state">
                {t('admin.edit.state')}
              </h3>
              {user.is_active ? (
                <Button
                  variant="default"
                  size="xs"
                  onClick={() => {
                    setActive.reset()
                    setConfirming(true)
                  }}
                  disabled={isMe}
                >
                  {t('admin.edit.disable')}
                </Button>
              ) : (
                <Button
                  variant="default"
                  size="xs"
                  onClick={() => toggle(true)}
                  loading={setActive.isPending}
                >
                  {t('admin.edit.enable')}
                </Button>
              )}
            </div>
            <p className="pd-hint">
              {isMe
                ? t('admin.edit.selfHint')
                : user.is_active
                  ? t('admin.edit.activeHint')
                  : t(
                      user.role === 'patient'
                        ? 'admin.edit.enableHintPatient'
                        : 'admin.edit.enableHint',
                    )}
            </p>
            {setActive.isError && <AdminErrorText error={setActive.error} />}
          </section>
        )}

        {!confirming && user.name === null && (
          <div className="pd-modal-foot">
            <Button variant="subtle" color="gray" onClick={onClose}>
              {t('admin.close')}
            </Button>
          </div>
        )}
      </div>
    </AdminModal>
  )
}
