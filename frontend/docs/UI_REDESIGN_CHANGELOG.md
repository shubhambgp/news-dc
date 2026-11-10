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
