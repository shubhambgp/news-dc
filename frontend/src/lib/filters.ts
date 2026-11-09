import { useSearchParams } from 'react-router'

import type { Params } from './api'

const FILTER_KEYS = ['category', 'content_type', 'source', 'min_quality'] as const

/** The shared item filters, read from the URL so a filtered feed can be shared and reloaded. */
export function useFilterParams(): Params {
  const [sp] = useSearchParams()
  return Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? undefined]))
}
