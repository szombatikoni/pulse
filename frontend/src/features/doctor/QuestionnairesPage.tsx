import { Button, Loader, Text, Title } from '@mantine/core'
import { ClipboardText, Plus } from '@phosphor-icons/react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { useQuestionnaireTemplates } from '../../api/plans'
import './patientDetail.css'
import './patientList.css'
import './questionnaireEditor.css'

/** A kérdőívek listája az orvosnak (M3, A5): soronként név, az érvényes verzió, a
 * kérdésszám és a legnagyobb pontszám, „Szerkesztés"; fent jobbra „Új kérdőív".
 * A sablonok közösek, bármely orvos szerkesztheti őket (D1). */
export function QuestionnairesPage() {
  const { t } = useTranslation()
  const templates = useQuestionnaireTemplates()

  return (
    <div className="pl-page">
      <header className="pl-ph">
        <div className="pl-ph-text">
          <span className="pl-eyebrow">{t('qeditor.list.eyebrow')}</span>
          <Title order={1} className="pl-title">
            {t('qeditor.list.title')}
          </Title>
          <div className="pl-ph-meta">
            <span>{t('qeditor.list.intro')}</span>
          </div>
        </div>
        <div className="pl-ph-actions">
          <Button component={Link} to="/doctor/questionnaires/new" leftSection={<Plus size={16} />}>
            {t('qeditor.list.add')}
          </Button>
        </div>
      </header>
      {templates.isPending && <Loader />}
      {templates.isError && <Text c="red">{t('errors.unavailable')}</Text>}
      {templates.isSuccess &&
        (templates.data.length === 0 ? (
          <p className="pl-no-match">{t('qeditor.list.empty')}</p>
        ) : (
          <section className="pl-plist" aria-label={t('qeditor.list.title')}>
            {templates.data.map((q) => (
              <div key={q.code} className="pulse-prow pl-row qe-row">
                <span className="pd-tico" aria-hidden="true">
                  <ClipboardText size={18} />
                </span>
                <span className="c-name">
                  <span className="pl-name">{q.name}</span>
                </span>
                <span className="qe-row-meta">
                  <span>{t('qeditor.list.valid', { n: q.version_no })}</span>
                  <span>{t('qeditor.questionCount', { count: q.question_count })}</span>
                  <span>{t('qeditor.list.maxScore', { n: q.max_score })}</span>
                </span>
                <Button
                  size="xs"
                  variant="default"
                  component={Link}
                  to={`/doctor/questionnaires/${q.code}`}
                  aria-label={t('qeditor.list.editLabel', { name: q.name })}
                >
                  {t('qeditor.list.edit')}
                </Button>
              </div>
            ))}
          </section>
        ))}
    </div>
  )
}
