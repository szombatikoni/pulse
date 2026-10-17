import { Anchor, Group, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { type PatientStatus, type PatientSummary, useDoctorPatients } from '../../api/patients'
import { StatusIcon, StatusLabel } from '../../components/StatusLabel'
import { STATUS_COLOR } from '../../components/statusColors'
import { formatRelative } from '../../format'
import { reasonText, uniqueReasons } from './reasons'

const KPI_ORDER: PatientStatus[] = ['severe', 'attention', 'no_data', 'handled', 'ok']
const LOUD: PatientStatus[] = ['severe', 'attention']

/** Státuszonkénti darabszám a lista fölött; a nullás tételek halványak. */
function StatusCounts({ patients }: { patients: PatientSummary[] }) {
  const { t } = useTranslation()
  return (
    <Group gap="xl">
      {KPI_ORDER.map((status) => {
        const count = patients.filter((p) => p.status === status).length
        return (
          <Group key={status} gap={6} opacity={count === 0 ? 0.45 : 1}>
            <StatusIcon status={status} />
            <Text
              fw={700}
              style={{ color: count && LOUD.includes(status) ? STATUS_COLOR[status] : undefined }}
            >
              {count}
            </Text>
            <Text size="sm" c="dimmed">
              {t(`status.${status}`)}
            </Text>
          </Group>
        )
      })}
    </Group>
  )
}

/** Az orvos priorizált beteglistája (F9): elöl a Súlyos, a végén a Rendben. */
export function DoctorPatientsPage() {
  const { t } = useTranslation()
  const patients = useDoctorPatients()

  if (patients.isPending) return <Loader />
  if (patients.isError) return <Text c="red">{t('errors.unavailable')}</Text>

  return (
    <Stack gap="md">
      <Title order={2}>{t('home.doctor.title')}</Title>
      {patients.data.length === 0 ? (
        <Text c="dimmed">{t('doctor.empty')}</Text>
      ) : (
        <>
          <StatusCounts patients={patients.data} />
          <Table highlightOnHover verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={140}>{t('doctor.columns.status')}</Table.Th>
                <Table.Th>{t('doctor.columns.patient')}</Table.Th>
                <Table.Th>{t('doctor.columns.reason')}</Table.Th>
                <Table.Th w={150}>{t('doctor.columns.lastData')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {patients.data.map((p) => {
                const [primary, ...others] = uniqueReasons(p.reasons)
                const loud = LOUD.includes(p.status)
                return (
                  <Table.Tr key={p.id}>
                    {/* Színcsík csak az orvosi döntést igénylő (Súlyos, Figyelem) soroknál. */}
                    <Table.Td
                      style={
                        loud ? { boxShadow: `inset 3px 0 0 ${STATUS_COLOR[p.status]}` } : undefined
                      }
                    >
                      <StatusLabel status={p.status} />
                    </Table.Td>
                    <Table.Td>
                      <Anchor component={Link} to={`/doctor/patients/${p.id}`} fw={600} c="inherit">
                        {p.name}
                      </Anchor>
                      <Text size="xs" c="dimmed">
                        {p.birth_date.slice(0, 4)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c={p.status === 'ok' ? 'dimmed' : undefined}>
                        {reasonText(t, primary)}
                      </Text>
                      {others.map((r, i) => (
                        <Group key={i} gap={6} mt={4} wrap="nowrap">
                          <StatusIcon status={r.status} size={12} />
                          <Text size="xs" c="dimmed">
                            {reasonText(t, r)}
                          </Text>
                        </Group>
                      ))}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {p.last_data_at ? formatRelative(t, p.last_data_at) : '—'}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  )
}
