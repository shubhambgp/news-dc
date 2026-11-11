import { expect, test, type Page, type Route } from '@playwright/test'

const item = (id: number, title: string, extra: Record<string, unknown> = {}) => ({
  id,
  title,
  url: `https://example.com/${id}`,
  publisher: 'Example News',
  author: null,
  published_at: '2026-11-08T10:00:00Z',
  source: { key: 'dcd', name: 'DatacenterDynamics' },
  primary_category: 'cooling',
  categories: ['cooling'],
  content_type: 'news',
  summary: `Summary of ${title}.`,
  tags: ['immersion'],
  relevance_score: 90,
  quality_score: 70,
  points: 12,
  comments_count: 3,
  discussion_url: 'https://news.ycombinator.com/item?id=1',
  ...extra,
})
const COOL = item(1, 'Immersion cooling retrofit at a colocation campus')
const GRID = item(2, 'Grid interconnection queue delays new campuses', { primary_category: 'power-energy', categories: ['power-energy'] })
const page1 = <T,>(items: T[]) => ({ items, page: 1, page_size: 20, total: items.length, has_more: false })
const topics = [
  { slug: 'cooling', name: 'Cooling', description: 'Cooling.', item_count: 1, latest: [COOL] },
  { slug: 'power-energy', name: 'Power & Energy', description: 'Power.', item_count: 1, latest: [GRID] },
]
const SSE = [
  ['sources', { sources: [{ n: 1, id: 1, title: COOL.title, url: COOL.url, publisher: 'Example News', published_at: COOL.published_at, source: COOL.source, primary_category: 'cooling', content_type: 'news' }] }],
  ['status', { stage: 'generating' }],
  ['token', { text: 'Operators are retrofitting immersion cooling ' }],
  ['token', { text: '[1].' }],
  ['done', { cited: [1], removed_citations: 0, truncated: false }],
]
  .map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`)
  .join('')

/** Mock every API route the flow touches. Records the For You request bodies. */
async function mockApi(page: Page, forYouBodies: unknown[]) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const p = url.pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (p === '/topics') return json(topics)
    if (p === '/feeds/foryou') {
      forYouBodies.push(route.request().postDataJSON())
      return json({ ...page1([{ ...COOL, kind: 'personal', reason: 'Because you follow Cooling', score: 1 }, { ...GRID, kind: 'discover', reason: 'Discover: Power & Energy', score: 0.5 }]), cold_start: false })
    }
    if (p === '/feeds/trending') return json(page1([GRID, COOL]))
    if (p === '/items/1') return json({ ...COOL, description: null, key_insights: [{ type: 'technical', text: 'Tanks cut cooling energy.' }], entities: { companies: ['Equinix'], technologies: [], locations: [] }, related_links: [], coverage: [], also_covered_by: [] })
    if (p === '/items/1/related') return json([{ ...GRID, similarity: 0.8, score: 0.8 }])
    if (p === '/search') return json({ ...page1([{ ...GRID, snippet: '<mark>Grid</mark> interconnection &amp; queues', score: 0.03 }]), mode: 'hybrid' })
    if (p === '/ask/suggestions') return json(['What is emerging in liquid cooling?'])
    if (p === '/ask') return route.fulfill({ status: 200, contentType: 'text/event-stream', body: SSE })
    if (p === '/stats') return json({ by_source: [{ key: 'dcd', name: 'DatacenterDynamics', items: 2, processed: 2 }] })
    return json({ error: { code: 'not_found', message: 'not mocked', request_id: 'x' } }, 404)
  })
}

test('home → pick topics → article → bookmark → bookmarks → search → ask', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const forYou: unknown[] = []
  await mockApi(page, forYou)

  // Home: onboarding picker on first visit.
  await page.goto('/')
  await page.getByRole('button', { name: 'Cooling', exact: true }).click()
  await page.getByRole('button', { name: /Show my feed/ }).click()
  await expect(page.getByText('What do you want to follow?')).toBeHidden()
  await expect(page.getByText('Because you follow Cooling')).toBeVisible()
  await expect(page.getByText('Discover', { exact: true })).toBeVisible()
  expect(forYou.at(-1)).toMatchObject({ explicitTopics: ['cooling'] })

  // Article: open from the feed, then bookmark it.
  await page.getByRole('main').getByRole('link', { name: COOL.title }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: COOL.title })).toBeVisible()
  await expect(page.getByText('Tanks cut cooling energy.')).toBeVisible()
  await expect(page.getByRole('link', { name: /Read original/ })).toHaveAttribute('href', COOL.url)
  await page.getByRole('button', { name: 'Bookmark', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Bookmarked' })).toBeVisible()

  // Bookmarks: keyboard shortcut "g b".
  await page.keyboard.press('g')
  await page.keyboard.press('b')
  await expect(page).toHaveURL(/\/bookmarks$/)
  await expect(page.getByRole('link', { name: COOL.title })).toBeVisible()

  // Search: "/" focuses the box; the state lives in the URL; the snippet is highlighted, not HTML.
  await page.keyboard.press('/')
  await page.keyboard.type('grid')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/search\?q=grid/)
  await expect(page.locator('mark', { hasText: 'Grid' })).toBeVisible()
  await expect(page.getByText('interconnection & queues')).toBeVisible()

  // Ask (mocked stream): the answer cites [1], which links to its source card.
  await page.keyboard.press('a')
  await expect(page).toHaveURL(/\/ask$/)
  await page.getByLabel('Your question').fill('Who is retrofitting immersion cooling?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Operators are retrofitting immersion cooling')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Source 1' })).toHaveAttribute('href', '#src-0-1')
  await expect(page.getByRole('list', { name: 'Sources' }).getByRole('link', { name: COOL.title })).toHaveAttribute('href', COOL.url)

  // Theme: "t" toggles and survives a reload; "?" opens the shortcuts help.
  await page.keyboard.press('Escape') // leave the question box
  const dark = await page.evaluate(() => document.documentElement.classList.contains('dark'))
  await page.keyboard.press('t')
  await page.reload()
  await expect(page.locator('html')).toHaveClass(dark ? /^(?!.*dark)/ : /dark/)
  // The theme class is set by an inline script before React mounts; wait for the app (and its key handler).
  await expect(page.locator('#site-search')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible()

  expect(errors).toEqual([])
})
