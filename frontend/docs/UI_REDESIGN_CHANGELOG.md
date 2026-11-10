# NewsDC 2.0 UI redesign changelog

Frontend only (`frontend/`). One entry per phase; plan in `UI_REDESIGN_PLAN.md`.

## Phase 0: audit and plan (2026-11-11)

- **Status:** done, pending human review.
- **Files:** added `frontend/docs/UI_REDESIGN_PLAN.md` and this changelog. No source file changed in this phase.
- **Audit method:**
  - Read the routes (`src/App.tsx`), the shell, the shared components, the theme provider, `index.html` and the CSP in `Caddyfile` (read only).
  - Took screenshots of `/`, `/trending`, `/article/1281`, `/ask`, `/dashboard`, `/admin` and `/search?q=cooling` at 1920×1080 and 375×812 in dark mode. The dev frontend's API calls were proxied to the live site's public `GET` endpoints, with `/ask` and `/admin` blocked.
  - Overflow check: none on any of the 14 captures.
  - Computed WCAG contrast for every pair in the brief's palette.
- **Main findings:**
  - At 1920 px the app is a 1280 px column.
  - Tablet gets the phone layout.
  - Theme flash on load.
  - No `viewport-fit=cover`, so iOS safe areas are 0.
  - Light-theme muted, cyan and green fail AA for small text.
  - White text on the dark primary is 2.5:1.
  - Real images, logos, reading time and a daily brief need backend data. Each one gets a frontend alternative (plan §2).
- **Round 1 (before this brief, D-039; commits `f5e98a8`, `46cbc9e`):** category-artwork cards, card grid, home hero, top story, trending strip, topic chips, the indigo theme, and the E2E flake fix (wait for the app to mount after reload). Checks then: lint, typecheck, Vitest 10, build, Playwright 6/6, Lighthouse accessibility 100 on 5 routes.

## Phase 1: design system (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/index.css`: tokens for both themes, ink tokens, type scale, radii, elevation, focus, `color-scheme`, the CSS tooltip, `.ai-block`.
  - `src/components/ui/button.tsx`: new `ai` variant, 44 px touch icon size.
  - `src/components/ui/badge.tsx`: tinted variants and an `overlay` variant.
  - `src/components/ui/card.tsx`: restyled.
  - `src/components/ui/input.tsx`: new `Input`, `Textarea`, `Select` and `fieldClass`.
  - `src/components/ui/tooltip.tsx`: new CSS-only `Tip`.
  - `src/components/common.tsx`: `TypeBadge` uses `Badge`; error and empty states restyled.
  - `src/components/ItemCard.tsx`: overlay badge, tooltips, tokens. The card no longer clips, so tooltips can escape it.
  - `src/components/Layout.tsx`: `ai` button, tooltips, field style, surfaces.
  - `src/components/Feed.tsx`: filters use `Select`.
  - `src/pages/Home.tsx`: round-1 gradients replaced by tokens.
  - `src/main.tsx`: Inter import.
  - `public/theme-init.js` (new) and `index.html`: no-flash theme, `theme-color`.
  - `package.json` and `pnpm-lock.yaml`: `@fontsource-variable/inter` 5.3.0 (exact).
  - `docs/UI_DESIGN_SYSTEM.md` (new). `docs/UI_REDESIGN_PLAN.md`: ink values; tooltip, dropdown and segmented-control notes.
- **Visual changes:**
  - The brief's palette in both themes; Inter.
  - Blue is the action colour, violet is AI-only.
  - Flat buttons (no gradients except artwork and the logo).
  - Tinted badges with AA-safe text.
  - Calmer error and empty states.
  - Native pickers and scrollbars follow the theme.
  - No white flash on load in dark mode.
- **Checks:**
  - `pnpm lint --deny-warnings`, `pnpm typecheck`: pass.
  - `pnpm test`: 10 passed.
  - `pnpm build`: pass. Main JS is 113.4 kB gzip, against 112.9 on `main`.
  - `pnpm e2e`: 1 passed.
  - No-flash check: the app bundle was blocked, so only `theme-init.js` could set the class. The `dark` class was correct in all 4 cases (system dark/light × stored none/dark/light).
  - Screenshots: 7 routes × 1440×900 and 375×812 × both themes, 28 captures, no blank page, no overflow.
  - Lighthouse 13.6 accessibility (light): 100 on `/`, `/trending`, `/topics`, `/bookmarks`, `/search?q=cooling`, `/article/1281`, `/dashboard`, `/ask`. The first run had 96–97 on three routes because the warning badge ink was 4.32:1; fixed by darkening the warning, data and success inks.
  - Dark contrast was computed, not measured by Lighthouse: base text at least 5.3:1, inks at least 7.75:1.
  - Lighthouse mobile performance, home: 90 (TBT 420 ms, CLS 0.046, LCP 0.9 s).
- **Changes from the plan:**
  - The tooltip is CSS-only, not Radix (17.6 kB gzip).
  - The dropdown menu and segmented control move to Phase 4, where they're first used.
  - Three light inks are darker than planned (table in `UI_DESIGN_SYSTEM.md`).
- **Remaining:**
  - Page-level files still use the older token names (`bg-card`, `bg-accent`, `bg-muted`). They map to the new tokens, so the colours are already right; each page is cleaned up in its own phase.
  - The article insight badges keep their old style until Phase 6.
  - The home "7-day activity" label truncates at 375 px (Phase 3).

## Phase 2: application shell (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/components/Layout.tsx`:
    - grid shell; the header and body share `--sidebar-w`
    - a new tablet icon `Rail`
    - the sidebar grouped as Browse / Library / Intelligence / Categories, with Admin pinned to the bottom
    - a wider search
    - the mobile bar with 56 px targets and safe area
    - the drawer with safe area
  - `src/index.css`: `.shell` widths per breakpoint (0, 72, 232, 248, 256, 264 px), the 2240 px shell cap, left/right safe-area padding, `3xl` (1920) and `4xl` (2560) breakpoints, and a right-side tooltip.
  - `src/components/common.tsx`:
    - new `WithAside` (right panel from 1280 px: 300 → 320 → 340 → 360 px)
    - `CardGrid` columns: 2 from a 576 px container, 3 from 896, 4 from 1280, 5 from 1792
  - `src/components/ItemCard.tsx`: the meta row wraps. Without the wrap, cards forced 16 px of horizontal scroll at 320 px.
  - `src/components/Feed.tsx`: grid cells get `min-w-0`.
  - `src/components/ui/tooltip.tsx`: new `side="right"`.
  - `src/pages/Home.tsx`: uses `WithAside`.
  - `index.html`: `viewport-fit=cover`, so `env(safe-area-inset-*)` works on iOS.
- **Layout per width:**

  | Width | Layout |
  |---|---|
  | < 768 | header (menu, logo, search, theme) + bottom bar + drawer |
  | 768–1023 | 72 px icon rail with hover labels, no bottom bar; feed in 2 columns |
  | ≥ 1024 | full sidebar; the logo column lines up with the sidebar and the search with the content |
  | 1920 | feed in 4 columns (3 next to the home panel) |
  | ≥ 2240 | the shell stops growing and centres |

- **Checks:**
  - lint, typecheck, Vitest 10, build: pass. Main JS 113.8 kB gzip.
  - Playwright: 3 out of 3 passed. It first failed on a strict-mode text clash: the sidebar group "Discover" matched the feed's "Discover" label. The group was renamed "Browse".
  - Screenshots: 8 routes at all 9 brief sizes in dark (72 captures), then tablet and laptop in both themes, plus the drawer at 375 px. QA responses are now cached per URL, because the first run hit the live API's 60/min limit at 768 px, which showed as "Too many requests".
  - Overflow: none, except `/dashboard` at 320 px (30 px). That one was already there in Phase 1 (26 px, Recharts panel) and is left for Phase 7.
  - Lighthouse accessibility: 100 on `/` and `/trending` for phone (bottom bar), desktop (sidebar) and 800 px (rail, `/` and `/topics`). Home mobile performance: 91 (TBT 360 ms, CLS 0.045).
- **Remaining:**
  - Page bodies are unchanged (Phases 3–7).
  - The home hero tiles stretch at 2560 px (Phase 3).
  - Dashboard overflow at 320 px (Phase 7).

## Phase 3: homepage (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/pages/Home.tsx`: rewritten.
  - `src/components/ArticleCards.tsx`: new `FeaturedCard`, `ArticleRow`, `TrendingRail`.
  - `src/components/SearchBox.tsx`: new; moved out of `Layout.tsx`, with an `id` prop and a large variant.
  - `src/components/Layout.tsx`: on the phone home page the header shows the brand instead of the search box; the sidebar reserves the categories' height while they load.
  - `src/components/Feed.tsx`: new `auto` prop. `false` means load more by button only.
- **Order** (the brief's): welcome line and live tiles → search (phones; desktop uses the header) → compact onboarding → featured story → AI briefing → Trending now → For You → Explore topics → Latest research.
- **Choices:**
  - **For You on home is not infinite:** 12 cards plus "Load more". The brief puts sections after it, and those can't be reached below an infinite feed.
  - **Right panel from 1280 px:** Your interests, Explore topics (with "Updated X ago" per topic) and Latest research (`/items?content_type=research`). Below 1280 px, the topics and research sections follow the feed, and "Your interests" is a pop-over next to the For You title.
  - **Onboarding:** one row of chips with category icons, scrolling with a fade at the edge, at every width. Phones put the buttons under the chips.
  - **Welcome tiles:** one row that scrolls on phones (was 2×2). The labels are shorter ("vs last week") and no longer truncate at 375 px.
  - **Briefing slot:**
    - When a weekly brief exists, it shows a violet "AI-generated" teaser: plain text from `content_md`, citations and Markdown stripped, rendered as text.
    - Otherwise it shows "Rising this week" from `/trends`, labelled as computed from tags and companies, with links to search. That is the case on the live site today.
    - No fake or hardcoded data anywhere: every number and item comes from the API.
- **Checks:**
  - lint, typecheck, Vitest 10, build: pass. Main JS 115.6 kB gzip.
  - Playwright: 2 out of 2 passed.
  - Screenshots: home at 7 sizes in both themes, then at 320/375/1024/1440/1920 in both themes after the fixes. No overflow, no blank page.
  - **CLS, desktop (Lighthouse `--preset=desktop`):** 0.224 at first, now **0.002**. Causes, found with `layout-shift` entries and a height comparison between loading and loaded:
    - the onboarding chips wrapped to 2–3 rows after load
    - skeletons shorter than the content (featured, trending rail, signals)
    - the aside's "Explore topics" appearing late
    - the sidebar's categories pushing "Admin" down
  - Desktop performance 96–97 (was 86), `/trending` 98.
  - Mobile: performance 100, accessibility 100, CLS 0, LCP 0.9 s. Machine load varied during this phase: the E2E time halved in the same run (8.5 s → 4.6 s), so the mobile TBT (60–70 ms, against 330–450 earlier) is not a like-for-like gain.
- **Remaining:**
  - The featured story is usually also the first For You card (both rank by trending). Removing it would mean filtering the server's ranking on the client; left as is.
  - Under the onboarding row, the native scrollbar shows on desktop.

## Phase 4: news discovery (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/components/Feed.tsx`:
    - new filter toolbar: content type chips; category, source and quality selects; "Clear filters (n)"; a "Filters" button on phones; a `toolbar` slot
    - `ViewToggle`
    - `Feed` gets `layout` (card/row), `featureFirst`, `countNoun` and a row skeleton; `render(item, layout)`
  - `src/components/ItemCard.tsx`:
    - new `row` layout with artwork on the left; the same `data-*` keyboard hooks
    - "Not interested" is hidden until hover only on devices that have hover. Before, it was invisible on touch tablets wider than 640 px.
  - `src/components/ui/segmented.tsx`: new segmented control (buttons with `aria-pressed` in a labelled group). It replaces the old `role="tab"` buttons, which had no tab panel.
  - `src/components/ArticleCards.tsx`: `FeaturedCard` is now a `data-card`, so `j`/`k`/`o`/`Shift+O` reach it.
  - `src/components/common.tsx`: `PageHeader` takes `description` and `icon`.
  - `src/lib/filters.ts`: `useSetParam`, `useView`. The view is kept in the URL (`view=list`).
  - `src/pages/Feeds.tsx` (Trending, Most relevant): descriptions that match the formulas in `docs/ARCHITECTURE.md`; 24h/7d/30d as a segmented control; on Trending, #1 as the featured card in grid view.
  - `src/pages/Search.tsx`: sort as a segmented control, view toggle, date fields in the field style, the result count, token-based `<mark>`, example queries when the box is empty, and a red alert for a bad date range.
- **Grid:** 1 column on phones, 2 on tablets, 3 on a standard desktop, 4 at 1920 px, up to 5 at 2560 px (container-based, Phase 2).
- **Checks:**
  - lint, typecheck, Vitest 10, build: pass. Main JS 117.0 kB gzip.
  - Playwright: pass.
  - Screenshots: Trending, Most relevant, Search (with and without a query) and the research list view at 375/768/1440/1920/2560 px in dark, then 320/375/430 px in both themes.
  - Overflow fixes found by the screenshots: the search toolbar (3 px) and the list-row source line (1 px) at 375 px. No overflow after the fixes.
  - Lighthouse (mobile): `/trending` accessibility 100 / performance 91, `/relevant` 100/97, `/search?q=…` 100/96, `/trending?view=list` 100/97. Desktop `/search`: 100/100. CLS 0 everywhere.
  - Keyboard (Playwright on live data): in grid and list view, `j` reaches the featured card and then the next card, `k` goes back, and `b` bookmarks a list row (`aria-pressed=true`).
  - The count is checked against the API: "100 articles in the last 7d" matches `/items?from=…` (100); without a window, `/feeds/trending` reports 2,073.
- **Remaining:**
  - On phones the search toolbar takes three short rows (types, Filters + sort, view).
  - The topic page sort select is restyled in Phase 5.

## Phase 5: topics and bookmarks (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/pages/Feeds.tsx` (`TopicsPage`, `TopicPage`):
    - **Topics:** artwork banner per topic; an activity badge from the newest item's date (Active today < 24 h, This week < 7 d, Quiet); "Updated X ago"; the article count; a share bar ("N% of topic labels", since an article can carry several categories, so the counts add up to more than the article total); the 3 latest articles; a container-based grid.
    - **Topic page:** breadcrumb; artwork banner with icon, description and article count (height reserved while it loads); sort as a segmented control (Latest, Trending, Relevant, Quality; `sort` stays in the URL); view toggle.
  - `src/pages/Bookmarks.tsx`:
    - Header with the count and JSON/Markdown export (unchanged logic).
    - Filters that run in the browser over the saved items: text, type, category (shown only when there's more than one), sort (recently saved or newest published), view toggle. All are kept in the URL.
    - Count line ("4 of 9 bookmarks").
    - An empty state with links to For You and Trending, and a no-match state with "Clear filters" (one URL update; three calls in one tick could overwrite each other).
    - Bookmark storage and the export format are untouched.
- **Checks:**
  - lint, typecheck, Vitest 10, build: pass. Main JS 117.05 kB gzip.
  - Playwright: pass.
  - Screenshots: `/topics`, `/topics/cooling` and `/topics/power-energy?sort=trending&view=list` at 375/768/1440/1920 px in both themes; `/bookmarks` (grid, and the filtered list) at 320/375/1440 px, seeded with 9 real items from `/feeds/relevant`. No overflow.
  - Lighthouse (mobile): `/topics` 97/100, `/topics/cooling` 90/100, `/topics/power-energy?view=list` 90/100, `/bookmarks` (empty) 97/100; desktop `/topics` 100/100. The topic pages first measured CLS 0.057 and 0.076 because the banner grew when its description loaded; now CLS 0 everywhere.
- **Not possible without the backend:** a real trend per topic. `/trends` covers tags, companies and technologies, not categories, so the badge uses recency instead.

## Phase 6: article detail and Ask AI (2026-11-11)

- **Status:** done, pending human review.
- **Files:**
  - `src/pages/Article.tsx`:
    - breadcrumb; artwork header with every category badge; headline up to 36 px at 1920 px; source row with an avatar, author, date and via
    - actions: Read original, Bookmark, **Share** (`navigator.share`, or copy the link with a "Link copied" confirmation), Not interested
    - **AI content is marked:** a violet `.ai-block` "AI summary" with an "AI-generated" badge, a word count and a disclaimer; "Key takeaways (AI-generated)" split into Technical insights and Business implications (two columns only when both exist)
    - **Publisher content is marked:** "From the publisher" (`item.description`, shown as a quote and attributed)
    - **Sources and coverage:** the original, every other source that found the URL, near-duplicates, the PDF
    - Discussion
    - right panel from 1280 px with Entities and tags and Related (compact rows); below that width both move inline
    - an article-shaped skeleton
  - `src/pages/Ask.tsx` (presentation only; the request, SSE handling, history and citation logic are unchanged):
    - empty state: icon, heading and suggestion cards in two columns
    - user bubble on the right; AI messages with an avatar, "NewsDC AI" and an "AI-generated · N sources" badge
    - retrieval and writing states with pulsing dots; source skeletons while retrieving; a blinking cursor while tokens stream
    - numbered source cards (the `src-{turn}-{n}` anchors are kept)
    - errors in an alert with "Ask again"
    - a composer pinned above the bottom bar and the safe area on phones and at the bottom on desktop, with an `ai` send button, a follow-up placeholder and the Enter/Shift+Enter hint
    - right panel "How answers work" from 1280 px
  - `src/components/Markdown.tsx`: citation chips use `primary-ink` (AA in light mode).
- **Not possible without the backend:** reading time. The API returns no article length, so the summary shows its own word count instead.
- **Checks:**
  - lint, typecheck, Vitest 10, build: pass. Main JS 117.0 kB gzip.
  - Playwright: pass. It covers the streamed answer, the `[1]` → `#src-0-1` anchor and the source link.
  - Screenshots: `/ask` (empty, and with an answer) and `/article/1281` at 320/375/430/768/1440/1920/2560 px in both themes. The answer screenshots use a canned SSE stream injected by the QA script, labelled "QA fixture answer" on screen, with real items as sources. No paid call was made. No overflow.
  - Lighthouse: mobile `/ask` 95/100 (CLS 0.022), `/article/1281` 91/100; desktop `/ask` 100/100, `/article/1281` 98/100.
