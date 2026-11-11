import { useSearchParams } from 'react-router'

import type { CardLayout } from '@/components/ItemCard'

import type { Params } from './api'

const FILTER_KEYS = ['category', 'content_type', 'source', 'min_quality'] as const

/** The shared item filters, read from the URL so a filtered feed can be shared and reloaded. */
export function useFilterParams(): Params {
  const [sp] = useSearchParams()
  return Object.fromEntries(FILTER_KEYS.map((k) => [k, sp.get(k) ?? undefined]))
}

/** URL-backed setter shared by the toolbar controls. Changing a filter drops `page`. */
export function useSetParam() {
  const [sp, setSp] = useSearchParams()
  const set = (k: string, v: string) =>
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (v) next.set(k, v)
        else next.delete(k)
        next.delete('page')
        return next
      },
      { replace: true },
    )
  return [sp, set] as const
}

/** Card grid or compact list, kept in the URL (`view=list`) like every other feed setting. */
export function useView(): [CardLayout, (v: CardLayout) => void] {
  const [sp, set] = useSetParam()
  return [sp.get('view') === 'list' ? 'row' : 'card', (v) => set('view', v === 'row' ? 'list' : '')]
}

