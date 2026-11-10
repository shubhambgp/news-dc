# NewsDC 2.0: frontend UI/UX redesign plan

Phase 0 output (audit and plan). Branch `feat/ui-redesign`. Date 2026-11-11.

**Scope:** files under `frontend/` only. No backend, API, database, AI, worker, Docker, Caddy or environment change. When a requirement needs one of those, this plan says so and uses a frontend-only alternative.

## 1. Audit

### 1.1 Stack and build

| Item | Current |
|---|---|
| Framework and build | React 19, Vite 8, TypeScript 7 (`tsc -b`), pnpm, Node 24 |
| Styling | Tailwind v4 (`@tailwindcss/vite`), shadcn tokens in `src/index.css`, `tw-animate-css` |
| UI primitives | `src/components/ui/{button,badge,card}.tsx` (shadcn, `cn` package, D-009). `radix-ui` is installed; only `Slot` is used today |
| Data | TanStack Query 5. `src/lib/api.ts` is the only API caller (typed client, SSE parser for `/ask`) |
| Routing | React Router 8, `src/App.tsx`, lazy routes |
| Charts | Recharts 3 (Dashboard only, its own chunk) |
| Icons | lucide-react 1.x |
| Dialogs | native `<dialog>` (D-036) |
| Tests | Vitest (`src/lib/profile.test.ts`, 10 tests), Playwright smoke (`e2e/smoke.spec.ts`, API mocked) |
| Lint | oxlint `--deny-warnings` (rule `only-export-components` applies) |
| CSP (Caddy, not editable here) | `script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data:`, `font-src 'self'`, `connect-src 'self'` |

### 1.2 Routes (unchanged by this work)

| Route | Page file | Data |
|---|---|---|
| `/` | `pages/Home.tsx` | `POST /feeds/foryou`, `/feeds/trending`, `/stats`, `/trends`, `/topics` |
| `/trending` | `pages/Feeds.tsx` `TrendingPage` | `/feeds/trending` + window |
| `/relevant` | `pages/Feeds.tsx` `RelevantPage` | `/feeds/relevant` |
| `/topics` | `pages/Feeds.tsx` `TopicsPage` | `/topics` |
| `/topics/:slug` | `pages/Feeds.tsx` `TopicPage` | `/topics/{slug}` + sort |
| `/article/:id` | `pages/Article.tsx` | `/items/{id}`, `/items/{id}/related` |
| `/search` | `pages/Search.tsx` | `/search` (filters, dates, sort) |
| `/bookmarks` | `pages/Bookmarks.tsx` | localStorage profile only |
| `/dashboard` | `pages/Dashboard.tsx` | `/stats`, `/trends`, `/export` links |
| `/ask` | `pages/Ask.tsx` | `/ask/suggestions`, `POST /ask` (SSE) |
| `/admin` | `pages/Admin.tsx` | `/admin/*` (cookie + CSRF) |
| `*` | `App.tsx` `NotFound` | none |

### 1.3 Layout, components and theme

- **Shell:** `components/Layout.tsx`. Sticky header, a 240 px sidebar from `lg` (1024 px), a drawer below `lg`, a bottom tab bar below `lg`, and the shortcut help dialog. Everything sits in `max-w-7xl` (1280 px).
- **Shared:** `components/ItemCard.tsx` (feed card), `Feed.tsx` (infinite list + `Filters`), `common.tsx` (Skeletons, Error/Empty states, `TypeBadge`, `Quality`, `PageHeader`, `Cover`, `CardGrid`), `Markdown.tsx` (safe Markdown for model output).
- **Theme:** `lib/theme.tsx`. `light | dark | system`, stored in localStorage, and the `.dark` class is set in a `useEffect`.
- **Breakpoints:** Tailwind defaults (`sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536), plus container queries in `CardGrid` (`@2xl`, `@4xl`).
- **Keyboard contract** (used by `useShortcuts`, must survive the redesign): `[data-card]`, `[data-open]`, `[data-bookmark]`, `[data-dismiss]`, `data-original`, `[data-card-page]`, `#site-search`.

### 1.4 State of the branch

This branch already has an uncommitted first pass (round 1, D-039 in `docs/DECISIONS.md`):
- article cards with category artwork
- the home hero, a "Top story" card, a numbered trending strip and topic chips
- an indigo/violet theme
- the E2E flake fix

This plan builds on that pass. Phase 1 replaces its palette with the one in the brief.

### 1.5 Current problems, from screenshots at 1920×1080 and 375×812 (dark)

| # | Problem | Where |
|---|---|---|
| P1 | At 1920 px the app is a 1280 px column with about 320 px empty on each side. The header actions stop at about 1130 px. | Shell, every page |
| P2 | The home hero and the topic picker push the news below the fold on a laptop. | Home |
| P3 | No right context panel at wide widths. On home it holds only "Your interests". | Home, Article |
| P4 | The article page is a plain text column: no header art, no visible line between AI text and publisher facts, and the action row has unequal weights. | Article |
| P5 | The Ask page is a narrow empty column at 1920. Suggestions are a plain list and the composer floats mid-page. | Ask |
| P6 | Dashboard charts use one colour, have no legends, and the category chart labels wrap into two lines. | Dashboard |
| P7 | Admin is plain tables and buttons; source health is text only. | Admin |
| P8 | Tablet (768–1023) gets the phone layout (drawer + bottom bar) with a wide single column. | Shell |
| P9 | Theme flash: `.dark` is applied after the first paint, so dark-mode users see a white frame. | `lib/theme.tsx` |
| P10 | Safe areas don't work on iOS: `index.html` has no `viewport-fit=cover`, so `env(safe-area-inset-*)` is 0. | `index.html` |
| P11 | The `theme-color` metas (`#ffffff` / `#0a0a0a`) don't match any palette. | `index.html` |
| P12 | Filters are native `<select>` elements in a row, with no visual grouping or "clear all". | Feeds, Search, Topic |
| P13 | Native `title` tooltips only (bookmark, dismiss, quality). | Cards |
| P14 | The chart tokens `--chart-1..5` are greys. | `index.css` |

Reference screenshots (the user's) show what to aim for: photo-led cards, a category pill on the image, the source with its logo and time, one clear primary action per card, and a compact mobile home with stat tiles, a featured story, a briefing banner, a trending strip and topic chips.

## 2. Hard limits (need a backend change, so not done)

| Requirement | Why it is blocked | Frontend alternative |
|---|---|---|
| Real article images | `items` has no image field. Adding one means a migration, an ingest change and a source-terms review, and the CSP `img-src` is `'self' data:` | Category artwork (`Cover`): gradient + icon per category. `ItemCard` takes an optional image prop, so photos plug in later |
| Publisher logos | No logo field; third-party favicon services are blocked by the CSP and would leak visits | Initial-letter avatar with a colour derived from the publisher name |
| Reading time | The API never returns `content_text` or a word count | Not shown. Labelled "AI summary · N words" from the summary instead |
| "AI **Daily** Briefing" | Briefs are weekly (`trend_briefs`, Monday 06:00 UTC) | "Weekly AI briefing", with its date range |
| Trending indicator per topic | `/trends` gives rising tags, companies and technologies, not categories | "Updated X ago" from each topic's newest item. Rising terms are shown in the right panel |
| Web fonts from a CDN | CSP `font-src 'self'` | Self-hosted font files bundled by Vite (see open question Q1) |

## 3. Design direction

A calm, information-dense intelligence workspace. Linear for the shell and spacing, Bloomberg for editorial hierarchy, Perplexity for Ask.

- **Content first:** the news is the hero. The welcome line is one line plus the stat tiles, not a banner.
- **One accent per job:** blue for actions and links, violet only for AI-generated things (summaries, briefing, Ask, "why" reasons), cyan for data and charts, green for success and health.
- **AI content is labelled:** every AI block gets a violet left rule, a sparkle icon and an "AI-generated" caption. Publisher facts (title, source, date, original link) stay neutral.
- **Gradients only on artwork:** cards and buttons are flat and use the tokens. This removes the round-1 CTA gradients.
- **Elevation by surface colour, not heavy shadows:** `background`, then `surface`, then `elevated`.

## 4. Design system (Phase 1)

Brief palette, with the contrast fixes from the audit (measured WCAG ratios):

| Token | Dark | Light | Notes |
|---|---|---|---|
| `--background` | `#080D19` | `#F6F8FC` | |
| `--surface` (`--card`) | `#101827` | `#FFFFFF` | |
| `--elevated` (`--muted`, `--accent`) | `#1B2A42` | `#F0F4FA` | |
| `--primary` | `#60A5FA` | `#2563EB` | dark: button text is `#080D19` (7.6:1); white on `#60A5FA` is only 2.5:1 |
| `--ai` | `#A78BFA` | `#7C3AED` | text OK on all surfaces (≥ 5.2:1) |
| `--data` (secondary accent) | `#22D3EE` | `#0891B2` | light is 3.3–3.7:1, so icons, charts and large text only; text uses `#155E75` (Phase 1: `#0E7490` was 4.4:1 on its tint) |
| `--success` | `#34D399` | `#059669` | light is 3.4–3.8:1, so icons only; text uses `#065F46` (Phase 1: `#047857` was 4.48:1 on its tint) |
| `--foreground` | `#F1F5F9` | `#172033` | |
| `--muted-foreground` | `#94A3B8` | `#64748B` → **`#5B6B80`** | `#64748B` is 4.48 on background and 4.31 on elevated (fails AA); `#5B6B80` passes on all three |
| `--border` | `#263449` | `#E2E8F0` | |

Also in Phase 1:
- typography scale (12/13/14/16/18/22/28/36)
- 4 px spacing grid
- radii (6, 10, 14, 20)
- three shadow levels
- focus ring (2 px `--ring` + offset)
- chart palette (blue, violet, cyan, green, amber)
- category hues kept for artwork only

Components (restyle of `ui/`, plus new pieces where none exist):

| Component | Status |
|---|---|
| Button (primary, secondary, ghost, outline, AI, destructive; sizes sm/md/lg/icon) | restyle |
| Input, Textarea | new |
| Select (native `<select>` kept, for accessibility and no dependency) | restyle |
| Card | restyle |
| Badge (category, content type, status) | restyle |
| Tooltip | new; **CSS-only** (Phase 1: Radix Tooltip added 17.6 kB gzip to the main bundle) |
| DropdownMenu for the filter "More" and sort menus | **moved to Phase 4**, where it is first used |
| Dialog (native `<dialog>`, D-036) | restyle |
| Segmented control (time windows, sorts) | **moved to Phase 4**, where it is first used |
| Skeleton, Empty and Error states | restyle |

Output: `frontend/docs/UI_DESIGN_SYSTEM.md`.

## 5. Responsive strategy (Phase 2 onward)

| Width | Navigation | Main | Right panel | Feed columns |
|---|---|---|---|---|
| 320–639 | bottom bar (5 tabs, safe area) + drawer for the rest | single column, 16 px gutters | none (content inlined or behind `<details>`) | 1 |
| 640–767 | same | 24 px gutters | none | 2 |
| 768–1023 (tablet) | **icon rail** (64 px) with tooltips; no bottom bar | fluid | none | 2 |
| 1024–1279 | full sidebar 232 px | fluid | none | 2–3 (container query) |
| 1280–1535 | sidebar 248 px | fluid | 300 px on Home, Article and Search | 3 |
| 1536–1919 | sidebar 256 px | fluid | 320 px | 3 |
| 1920–2559 | sidebar 264 px | fluid | 340 px | 4 |
| ≥ 2560 | shell capped at **2240 px** and centred; text capped at about 72ch | | 360 px | 4 (cards capped at about 420 px) |

Rules:
- The shell becomes a CSS grid (`sidebar | main | aside`) and the 1280 px `max-w-7xl` goes.
- Grid columns follow the container (`@container`), so the same card grid fits in main, beside a panel or full width.
- Reading text stays at most about 72ch (article body, AI answer) at every width.
- Touch targets are at least 44 px below `md`.

## 6. Phases, files and dependencies

| Phase | Builds on | Main files (all under `frontend/`) |
|---|---|---|
| 1 Design system | 0 | `src/index.css`, `src/components/ui/*` (button, badge, card, new input, tooltip, dropdown, segmented), `src/components/common.tsx`, `src/lib/category.ts`, `index.html` (theme-color), `public/theme-init.js` (no-flash theme, external file so it fits `script-src 'self'`), `docs/UI_DESIGN_SYSTEM.md` |
| 2 Shell | 1 | `src/components/Layout.tsx` (grid shell, rail, sidebar, header, mobile bar, drawer), `index.html` (`viewport-fit=cover`) |
| 3 Home | 1, 2 | `src/pages/Home.tsx`, new `src/components/article/` (`FeaturedCard`, `ArticleCard` = today's `ItemCard`, `ArticleRow`, `TrendingRail`), `ItemCard.tsx` re-export |
| 4 Discovery | 3 | `src/pages/Feeds.tsx` (Trending, Relevant, Topic), `src/pages/Search.tsx`, `src/components/Feed.tsx` (filter toolbar, card/list view toggle) |
| 5 Topics, Bookmarks | 3, 4 | `src/pages/Feeds.tsx` (`TopicsPage`), `src/pages/Bookmarks.tsx` (client-side filters over the stored bookmarks; storage logic untouched) |
| 6 Article, Ask | 3 | `src/pages/Article.tsx`, `src/pages/Ask.tsx`, `src/components/Markdown.tsx` (styles only) |
| 7 Dashboard, Admin | 1, 2 | `src/pages/Dashboard.tsx`, `src/pages/Admin.tsx` |
| 8 QA | all | `docs/RESPONSIVE_QA_REPORT.md`, fixes anywhere above |

`docs/UI_REDESIGN_CHANGELOG.md` is updated at the end of every phase.

Not touched: `src/lib/api.ts` (except types, if a presentational helper needs one; no request change), `src/lib/profile.ts`, `src/lib/filters.ts`, `src/App.tsx` route table, the `vite.config`, and everything outside `frontend/`.

Page-wise scope beyond the brief's lists:
- **Home** follows the brief's order: welcome line + tiles → search (inline on mobile, header search on desktop) → compact onboarding (one row of chips that scrolls, with "Show my feed") → featured → weekly briefing → trending rail → For You → explore topics → latest research (`GET /items?content_type=research`, an existing endpoint and filter).
- **Article:**
  - breadcrumb
  - header art
  - meta row: source, author, date, via
  - AI block: summary, then key insights split into "Technical" and "Business"
  - entities and tags
  - discussion and coverage ("also covered by")
  - related articles in the right panel at ≥ 1280
  - actions: Read original, Bookmark, Share (`navigator.share`, with a clipboard fallback), Not interested
- **Ask:** a two-pane workspace at ≥ 1280 (conversation, plus a sources panel for the current answer). Mobile gets a full-height layout, a composer pinned above the safe area, and suggestion chips.
- **Dashboard:**
  - KPI tiles
  - per-day area chart with a gradient fill
  - a coloured funnel
  - category bars with single-line labels (truncated, full name in a tooltip)
  - content type as a donut with a legend
  - rising terms as small tables with arrows
- **Admin:**
  - status dots for source health (`last_error`, `admin_disabled`)
  - toolbar actions
  - sticky table headers and horizontal scroll inside the table on mobile
  - job status badges

## 7. Risks and validation

| Risk | Mitigation |
|---|---|
| Breaking keyboard shortcuts or the E2E flow | Keep the `data-*` contract and the accessible names the E2E uses ("What do you want to follow?", "Show my feed", "Discover", "Your question", "Ask", "Source 1", list "Sources", dialog "Keyboard shortcuts", `#site-search`). Run `pnpm e2e` every phase |
| Contrast regressions with the new palette | Fixes in §4. Lighthouse accessibility on 7 routes each phase (target 100) |
| Performance (more DOM, a font) | Lighthouse mobile home ≥ 85 (plan §9E target). Fonts self-hosted, `font-display: swap`, latin subset only |
| Lint rule `only-export-components` | Helpers in `src/lib/`, components in `src/components/` |
| `radix-ui` Tooltip/Dropdown adding bundle weight | Imported per component; checked in the `pnpm build` output |
| QA needs data for Admin and Ask without paid or admin calls | The local QA script proxies public GETs to the live site and mocks `/admin/*` and `POST /ask` in the browser (test-only, nothing mocked in the app) |

Checks for every phase:
- `pnpm lint --deny-warnings && pnpm typecheck && pnpm test && pnpm build && pnpm e2e`
- screenshots at the brief's 9 sizes (the major ones per phase, all in Phase 8), both themes
- an overflow check (`scrollWidth > innerWidth`)
- Lighthouse on home

## 8. Open questions for the human (before Phase 1)

- **Q1 Font.** The CSP allows only self-hosted fonts. Recommendation: Inter Variable via `@fontsource-variable/inter` (one frontend dependency, about 48 kB woff2 latin, bundled by Vite), or keep system fonts (no dependency).
- **Q2 Docs location.** These redesign docs are in `frontend/docs/` to stay in scope. CLAUDE.md asks for deviations in the repo-level `docs/DECISIONS.md` (D-039 was added there in round 1). Keep D-039 there and add to it, or move it?
- **Q3 Round 1 baseline.** Commit the round-1 work first (`feat(ui): …`, `test(e2e): …`) so each phase is a separate commit?
