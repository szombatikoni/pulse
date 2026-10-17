import { Loader, Table, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'

import { usePatientMeasurements } from '../../api/measurements'
import { formatDateTime, formatMeasurementValue } from '../../format'

/** A beteg méréseinek listája, a legújabb elöl (F5; a grafikon az M3-ban). */
export function MeasurementHistory({ patientId }: { patientId: string }) {
  const { t } = useTranslation()
  const measurements = usePatientMeasurements(patientId)

  if (measurements.isPending) return <Loader size="sm" />
  if (measurements.isError) return <Text c="red">{t('errors.unavailable')}</Text>
  if (measurements.data.length === 0) return <Text c="dimmed">{t('measurements.empty')}</Text>

  return (
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t('measurements.columns.time')}</Table.Th>
          <Table.Th>{t('measurements.columns.type')}</Table.Th>
          <Table.Th>{t('measurements.columns.value')}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {measurements.data.map((m) => (
          <Table.Tr key={m.id}>
            <Table.Td>{formatDateTime(m.measured_at)}</Table.Td>
            <Table.Td>{t(`measurementTypes.${m.type_code}`)}</Table.Td>
            <Table.Td>{formatMeasurementValue(t, m)}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
