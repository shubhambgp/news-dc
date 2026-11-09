import { describe, expect, it } from 'vitest'

import { parseSse } from './api'
import { LIMITS, applyEvent, decay, emptyProfile, parseProfile, removeBookmark, setTopics, toRequest } from './profile'

const DAY = 86_400_000
const T0 = Date.UTC(2026, 10, 9)
const item = (id: number, categories = ['cooling'], tags = ['immersion']) => ({ id, categories, tags })

describe('applyEvent', () => {
  it('adds +1 open, +2 read, +3 bookmark, -3 dismiss to categories and tags', () => {
    let p = emptyProfile(T0)
    p = applyEvent(p, 'open', item(1, ['cooling', 'power-energy']))
    expect(p.categoryWeights).toEqual({ cooling: 1, 'power-energy': 1 })
    expect(p.tagWeights).toEqual({ immersion: 1 })
    p = applyEvent(p, 'read', item(1))
    p = applyEvent(p, 'bookmark', item(2))
    expect(p.categoryWeights.cooling).toBe(6)
    p = applyEvent(p, 'dismiss', item(3, ['networking'], ['ai']))
    expect(p.categoryWeights.networking).toBe(-3)
    expect(p.readIds).toEqual([1])
    expect(p.bookmarkIds).toEqual([2])
    expect(p.dismissedIds).toEqual([3])
  })

  it('moves a re-read item to the end and keeps the newest 200 reads', () => {
    let p = emptyProfile(T0)
    for (let i = 1; i <= LIMITS.read + 10; i++) p = applyEvent(p, 'open', item(i, [], []))
    expect(p.readIds).toHaveLength(LIMITS.read)
    expect(p.readIds[0]).toBe(11)
    p = applyEvent(p, 'open', item(50, [], []))
    expect(p.readIds.at(-1)).toBe(50)
    expect(p.readIds.filter((x) => x === 50)).toHaveLength(1)
  })

  it('keeps at most 100 tags (largest |weight|) and clamps weights to ±1000', () => {
    let p = emptyProfile(T0)
    for (let i = 0; i < 150; i++) p = applyEvent(p, 'open', item(i + 1, [], [`t${i}`]))
    p = applyEvent(p, 'bookmark', item(999, [], ['strong']))
    expect(Object.keys(p.tagWeights)).toHaveLength(LIMITS.tags)
    expect(p.tagWeights.strong).toBe(3)
    for (let i = 0; i < 400; i++) p = applyEvent(p, 'bookmark', item(5, ['cooling'], []))
    expect(p.categoryWeights.cooling).toBe(1000)
  })

  it('ignores tags the server would reject (over 64 chars)', () => {
    const p = applyEvent(emptyProfile(T0), 'open', item(1, [], ['x'.repeat(65), 'ok']))
    expect(Object.keys(p.tagWeights)).toEqual(['ok'])
  })
})

describe('decay', () => {
  it('multiplies weights by 0.95 per whole day and drops tiny ones', () => {
    const p = { ...emptyProfile(T0), categoryWeights: { cooling: 10, tiny: 0.01 } }
    expect(decay(p, T0 + DAY / 2)).toBe(p) // less than a day: unchanged
    const d = decay(p, T0 + 2 * DAY + 5)
    expect(d.categoryWeights.cooling).toBeCloseTo(10 * 0.95 ** 2, 3)
    expect(d.categoryWeights.tiny).toBeUndefined()
    expect(d.decayedAt).toBe(T0 + 2 * DAY) // the remainder of a day carries over
  })
})

describe('parseProfile', () => {
  it('falls back to an empty profile on garbage', () => {
    expect(parseProfile('not json', T0)).toEqual(emptyProfile(T0))
    expect(parseProfile(null, T0)).toEqual(emptyProfile(T0))
  })

  it('drops invalid fields and enforces the limits on stored data', () => {
    const raw = JSON.stringify({
      categoryWeights: { cooling: 2, bad: 'x' },
      readIds: [...Array.from({ length: 250 }, (_, i) => i + 1), -1, 1.5],
      dismissedIds: 'nope',
      explicitTopics: ['cooling', 3],
      onboarded: true,
      decayedAt: T0,
    })
    const p = parseProfile(raw, T0)
    expect(p.categoryWeights).toEqual({ cooling: 2 })
    expect(p.readIds).toHaveLength(LIMITS.read)
    expect(p.readIds.at(-1)).toBe(250)
    expect(p.dismissedIds).toEqual([])
    expect(p.explicitTopics).toEqual(['cooling'])
    expect(p.onboarded).toBe(true)
  })

  it('applies the decay owed since the last visit', () => {
    const raw = JSON.stringify({ categoryWeights: { cooling: 10 }, decayedAt: T0 - 3 * DAY })
    expect(parseProfile(raw, T0).categoryWeights.cooling).toBeCloseTo(10 * 0.95 ** 3, 3)
  })
})

describe('toRequest', () => {
  it('sends only server fields and drops unknown categories', () => {
    let p = setTopics(emptyProfile(T0), ['cooling', 'gone', 'cooling'])
    p = applyEvent(p, 'bookmark', item(7, ['cooling', 'gone']))
    p = removeBookmark(p, 7)
    const body = toRequest(p, new Set(['cooling']))
    expect(Object.keys(body).sort()).toEqual(
      ['bookmarkIds', 'categoryWeights', 'dismissedIds', 'explicitTopics', 'readIds', 'tagWeights'].sort(),
    )
    expect(body.explicitTopics).toEqual(['cooling'])
    expect(body.categoryWeights).toEqual({ cooling: 3 })
    expect(body.bookmarkIds).toEqual([])
  })
})

describe('parseSse', () => {
  it('returns complete events and keeps the partial remainder', () => {
    const { events, rest } = parseSse(
      'event: sources\ndata: {"sources":[]}\n\nevent: token\ndata: {"text":"Hi"}\n\nevent: tok',
    )
    expect(events).toEqual([
      { event: 'sources', data: { sources: [] } },
      { event: 'token', data: { text: 'Hi' } },
    ])
    expect(rest).toBe('event: tok')
  })
})
