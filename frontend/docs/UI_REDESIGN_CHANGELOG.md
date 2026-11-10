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
- **Round 1 (before this brief, uncommitted, D-039):** category-artwork cards, card grid, home hero, top story, trending strip, topic chips, the indigo theme, and the E2E flake fix (wait for the app to mount after reload). Checks then: lint, typecheck, Vitest 10, build, Playwright 6/6, Lighthouse accessibility 100 on 5 routes.
