import { Button, Loader, Text, Textarea } from '@mantine/core'
import { Plus } from '@phosphor-icons/react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { NOTE_TEXT_MAX, useAddNote, usePatientNotes } from '../../api/notes'
import { StatusIcon } from '../../components/StatusLabel'
import { formatDateTime } from '../../format'

/** A szövegmező azonosítója: a fejléc „Megjegyzés” gombja ide görget és fókuszál. */
export const NOTE_FIELD_ID = 'pd-note-text'

/** Az orvosok megjegyzései a betegről (M3, A8; F16), felületterv: notesCard. A
 * legújabb elöl, a szerző nevével és az időponttal. Csak hozzáírható: nincs
 * szerkesztés és törlés (A8 D2); a beteg nem látja. A nyitott állapotot és a
 * piszkozatot az adatlap tartja: a fejléc gombja is ezt nyitja, és a fülváltás
 * (a kártya lebomlása) után a beírt szöveg megmarad. */
export function NotesCard({
  patientId,
  open,
  text,
  onTextChange,
  onOpen,
  onClose,
}: {
  patientId: string
  open: boolean
  text: string
  onTextChange: (text: string) => void
  onOpen: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const notes = usePatientNotes(patientId)
  const add = useAddNote(patientId)
  const setText = onTextChange

  const cancel = () => {
    setText('')
    add.reset()
    onClose()
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = text.trim()
    if (!value) {
      document.getElementById(NOTE_FIELD_ID)?.focus()
      return
    }
    add.mutate(value, {
      onSuccess: () => {
        setText('')
        onClose()
      },
    })
  }

  return (
    <section className="pd-card" id="pd-notes" aria-labelledby="pd-h-notes">
      <div className="pd-card-head">
        <div className="left">
          <h2 className="pd-h-card" id="pd-h-notes">
            {t('doctor.notes.title')}
          </h2>
          <span className="pd-meta">{t('doctor.notes.meta')}</span>
        </div>
        {!open && (
          <Button size="xs" variant="default" leftSection={<Plus size={14} />} onClick={onOpen}>
            {t('doctor.notes.add')}
          </Button>
        )}
      </div>
      <div className="pd-notes">
        {open && (
          <form className="pd-note-form" onSubmit={submit} noValidate>
            <Textarea
              id={NOTE_FIELD_ID}
              aria-label={t('doctor.notes.newLabel')}
              placeholder={t('doctor.notes.placeholder')}
              value={text}
              onChange={(e) => setText(e.currentTarget.value)}
              maxLength={NOTE_TEXT_MAX}
              autosize
              minRows={3}
              maxRows={10}
            />
            {add.isError && (
              <span className="pd-err" role="alert">
                <StatusIcon status="severe" size={14} />
                {t('doctor.notes.error')}
              </span>
            )}
            <div className="pd-plan-foot">
              <Button variant="subtle" color="gray" onClick={cancel}>
                {t('doctor.plan.cancel')}
              </Button>
              <Button type="submit" loading={add.isPending}>
                {t('doctor.notes.save')}
              </Button>
            </div>
          </form>
        )}
        {notes.isPending && <Loader size="sm" />}
        {notes.isError && <Text c="red">{t('errors.unavailable')}</Text>}
        {notes.isSuccess &&
          (notes.data.length === 0 ? (
            <p className="pd-muted">{t('doctor.notes.empty')}</p>
          ) : (
            <ol className="pd-note-list" aria-label={t('doctor.notes.title')}>
              {notes.data.map((note) => (
                <li key={note.id} className="pd-note">
                  <span className="txt">{note.text}</span>
                  <span className="by">
                    {note.author.name} · {formatDateTime(note.created_at)}
                  </span>
                </li>
              ))}
            </ol>
          ))}
      </div>
    </section>
  )
}
