# NewsDC 2.0 responsive and visual QA report

Phase 8 of the redesign (`UI_REDESIGN_PLAN.md`), 2026-11-11, branch `feat/ui-redesign`. Every check here was run by the agent. **No human has reviewed the UI yet.**

## Method

- **Build under test:** the Vite dev server at `:5199`, plus a production build under `vite preview` at `:4173` for Lighthouse.
- **Data:** API calls were proxied to the live site's public read-only endpoints (`https://news-dc.atinus.co/api/v1/*`), so every page shows real data. Responses were cached per URL during a run, to stay under the API's rate limit.
- **No paid or admin calls were made.** `POST /ask` and `/admin/*` never reached the live site:
  - **Ask:** the answer screenshots use a canned SSE stream injected by the QA script, with real items as sources. The answer text reads "QA fixture answer (mocked stream)".
  - **Admin:** the screenshots use mocked responses. Source names, categories and runs are real public data from `/stats` and `/topics`; the session, jobs and rejected rows are labelled "QA fixture".
  - **Bookmarks:** seeded in localStorage with 9 real items from `/feeds/relevant`.
  - None of this mocking is in the app. It lives only in the QA scripts, which stay outside the repo.
- **Browser:** Chrome 157 (Playwright 1.65, `channel: chrome`) and Lighthouse 13.6.0.

## Matrix

13 routes × 9 viewports × 2 themes = **234 screenshots**.

- **Routes:** `/`, `/trending`, `/relevant`, `/topics`, `/topics/cooling`, `/article/1281`, `/search?q=liquid cooling`, `/search` (empty), `/bookmarks`, `/dashboard`, `/ask` (with an answer), `/admin` (signed in), `/does-not-exist`.
- **Viewports:** 320×700, 375×812, 430×932, 768×1024, 1024×768, 1280×800, 1440×900, 1920×1080, 2560×1440.
- **Themes:** dark and light (`prefers-color-scheme`).

Automatic checks on every capture:
- horizontal overflow (`scrollWidth > innerWidth`)
- blank page (body text under 80 characters)
- uncaught page errors

**Final run:** 234 of 234 OK. No overflow, no blank page, no page error.

### Extra audits at 375×812 and 1440×900 (8 routes)

| Check | First run | Final |
|---|---|---|
| Interactive targets under 24 px (WCAG 2.5.8; inline links in running text and full-card stretched links exempt) | 10 to 30 per route (category badges 22 px, comment counts 16 px, "See all" 16 px, breadcrumbs 15 px, tags 20 px, "Show as table" 16 px, rising-term links 20 px) | **0 on every route** |
| Unintended clipping (overflow hidden without ellipsis or line clamp) | 0 | 0 |
| Visible focus after Tab | Flags on `/ask` and `/topics` | Checked by screenshot. The flags were false positives: the ring is drawn on a parent (`focus-within` on the Ask composer) or a child (the bottom-bar pill). Cards whose title link covers the whole card now also ring the card (`has-[:focus-visible]`), which was weak before (underline only) |

### Lighthouse 13.6 (production build, final)

| Route | Mode | Performance | Accessibility | Best practices | SEO | CLS |
|---|---|---|---|---|---|---|
| `/` | mobile | 100 | 100 | 100 | 100 | 0 |
| `/trending` | mobile | 91 | 100 | 100 | 100 | 0 |
| `/relevant` | mobile | 97 | 100 | 100 | 100 | 0 |
| `/topics` | mobile | 97 | 100 | 100 | 100 | 0 |
| `/topics/cooling` | mobile | 90 | 100 | 100 | 100 | 0 |
| `/article/1281` | mobile | 93 | 100 | 100 | 100 | 0 |
| `/search?q=liquid cooling` | mobile | 96 | 100 | 100 | 100 | 0 |
| `/bookmarks` (empty) | mobile | 97 | 100 | 100 | 100 | 0 |
| `/dashboard` | mobile | 79 | 100 | 100 | 100 | 0 |
| `/ask` | mobile | 95 | 100 | 96 ¹ | 100 | 0.022 |
| `/admin` | mobile | 92 | 100 | 96 ¹ | 63 ² | 0 |
| `/` | desktop | 98 | 100 | 100 | 100 | 0.002 |
| `/trending` | desktop | 98 | 100 | 100 | 100 | 0 |
| `/article/1281` | desktop | 98 | 100 | 100 | 100 | 0 |
| `/dashboard` | desktop | 98 | 100 | 100 | 100 | 0 |
| `/ask` | desktop | 100 | 100 | 96 ¹ | 100 | 0.006 |

1. "errors-in-console" comes from the QA proxy, which answers `/ask/*` and `/admin/*` with 503. Not an app error.
2. `robots.txt` disallows `/admin` on purpose (unchanged).

Lighthouse checks only the light theme. Dark-theme contrast was computed from the tokens: base text is at least 5.3:1 and badge inks at least 7.75:1 (`UI_DESIGN_SYSTEM.md`). Performance numbers vary with machine load during a run (in Phase 3, the same E2E took 8.5 s in one run and 4.6 s in another), so compare them only within one table.

## 1440 px vs 1920 px

| | 1440 × 900 | 1920 × 1080 |
|---|---|---|
| Shell | 248 px sidebar + content + 300 px right panel (home, article, Ask) | 264 px sidebar + content + 340 px panel; the old 1280 px cap (about 320 px empty on each side) is gone |
| Feed grid | 3 columns on Trending, Relevant and Search; 2 next to the home panel | 4 columns; 3 next to the home panel |
| Featured / top story | artwork 5/12, text 7/12 | the same proportions; the headline stays within 3 lines |
| Article | 768 px reading column, entities and related on the right | the same column (readable line length), headline 36 px |
| Dashboard | 2-column panel grid | 3 columns, per-day chart full width and taller |
| Ask | 768 px conversation, "How answers work" on the right | 896 px conversation |

At 2560 × 1440 the shell stops at 2240 px and centres, and feeds use 4 to 5 columns of 300 to 420 px cards.

## Issues found and fixed during the redesign

| Phase | Issue | Fix |
|---|---|---|
| 1 | Brief's light muted, cyan, green and warning text below AA | darker light-mode ink tokens |
| 1 | White flash on load in dark mode | `public/theme-init.js` before the bundle |
| 1 | Radix Tooltip +17.6 kB gzip | CSS-only tooltip |
| 2 | 16 px horizontal scroll at 320 px (card meta row) | row wraps; grid cells `min-w-0` |
| 2 | Tablet got one giant column | 2 columns from a 576 px container |
| 2 | "Discover" group name collided with the feed's "Discover" label | group renamed "Browse" |
| 3 | Desktop CLS 0.224 on home (0.155 on `main` before the redesign) | skeletons sized to the content, sidebar categories reserved, single-row onboarding; now 0.002 |
| 4 | 1–3 px overflow at 375 px (toolbar, list row) | wrap and `min-w-0` |
| 4 | "Not interested" invisible on touch tablets | hover-hide only where hover exists |
| 5 | Topic page CLS 0.06–0.08 | banner lines reserved |
| 6 | Citation chips below AA in light mode | `primary-ink` |
| 7 | Chart tooltips transparent since Phase 1 (removed `--popover`/`--muted`) | `--surface`/`--elevated` |
| 7 | Dashboard 26–30 px overflow at 320 px (open since Phase 1) | Rising columns `min-w-0` |
| 7 | Admin 107–162 px overflow on phones: an `sr-only` label escaped the table scroller | scroller `relative` |
| 8 | Touch targets under 24 px across cards and pages | `min-h-6` / padding on badges, counts, breadcrumbs, tags, links |
| 8 | Weak focus on full-card links (underline only) | card ring via `has-[:focus-visible]` |
| 8 | Ask conversation narrow at 1920+ | 896 px from 1920 px |

## Known limitations

- **Article photos, publisher logos and reading time:** not available without backend data (plan §2). Category artwork, an initial-letter avatar and the summary's word count are used instead.
- **Briefing slot:** weekly, not daily (the brief is written on Mondays). When there is no brief, the slot shows "Rising this week" from `/trends`, labelled as computed.
- **Per-topic trend:** not in the API. The topic badges use the newest item's age.
- **Dashboard mobile performance (79–82):** held back by the Recharts chunk (114.6 kB gzip, about the same before the redesign).
- **Browsers:** Safari, Firefox and real iOS/Android devices were not tested. Safe areas are coded (`viewport-fit=cover`, `env()`), but no device with a notch was used.
- **Where the extra audits ran:** touch targets, clipping and focus were audited on 8 routes at 375 and 1440 px, not on all 234 captures.
- **Human review is pending** for both themes at phone width, the 1920/2560 layouts, and the AI vs publisher labelling on articles.
