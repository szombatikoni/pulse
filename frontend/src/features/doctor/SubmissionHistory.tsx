import { Loader, Table, Text, Tooltip } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { usePatientSubmissions } from '../../api/questionnaires'
import { formatDateTime } from '../../format'

/** A beteg kérdőív-kitöltései pontszámmal és sávval (csak az orvos látja).
 * A pontszám fölé víve a válaszok és a kérdésenkénti pontok látszanak. */
export function SubmissionHistory({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const submissions = usePatientSubmissions(patientId)

  if (submissions.isPending) return <Loader size="sm" />
  if (submissions.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  if (submissions.data.length === 0) return <Text c="dimmed">{t('questionnaires.empty')}</Text>

  return (
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t('questionnaires.columns.time')}</Table.Th>
          <Table.Th>{t('questionnaires.columns.questionnaire')}</Table.Th>
          <Table.Th>{t('questionnaires.columns.score')}</Table.Th>
          <Table.Th>{t('questionnaires.columns.band')}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {submissions.data.map((s) => (
          <Table.Tr key={s.id}>
            <Table.Td>{formatDateTime(s.submitted_at)}</Table.Td>
            <Table.Td>
              {s.questionnaire_name}{' '}
              <Text span size="xs" c="dimmed">
                {t('questionnaires.version', { version: s.version_no })}
              </Text>
            </Table.Td>
            <Table.Td>
              <Tooltip
                multiline
                w={360}
                label={s.answers
                  .map((a) => `${a.order_no}. ${a.text} — ${a.label} (${a.score})`)
                  .join('\n')}
                style={{ whiteSpace: 'pre-line' }}
              >
                <Text span size="sm" style={{ cursor: 'help' }}>
                  {s.total_score} / {s.max_score}
                </Text>
              </Tooltip>
            </Table.Td>
            <Table.Td>{t(`questionnaires.bands.${s.band}`, { defaultValue: s.band })}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
