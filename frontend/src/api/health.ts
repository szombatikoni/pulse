import { useQuery } from '@tanstack/react-query'

import { apiGet } from './client'

export type Health = { status: string; database: string }

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => apiGet<Health>('/health') })
}
