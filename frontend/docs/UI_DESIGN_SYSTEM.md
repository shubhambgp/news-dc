# NewsDC design system

Phase 1 of the NewsDC 2.0 redesign. Source of truth: `src/index.css` (tokens) and `src/components/ui/` (primitives). Use the utilities below and don't hardcode colours in components.

## Colour tokens

Every token exists in both themes. Light values are on `:root`; dark values are on `.dark`, which `public/theme-init.js` sets before the first paint.

| Utility | Token | Dark | Light | Use |
|---|---|---|---|---|
| `bg-background` | `--background` | `#080D19` | `#F6F8FC` | page |
| `bg-surface` (= `bg-card`) | `--surface` | `#101827` | `#FFFFFF` | cards, panels, inputs, dialogs |
| `bg-elevated` (= `bg-muted`, `bg-accent`) | `--elevated` | `#1B2A42` | `#F0F4FA` | hover, chips, skeletons, kbd |
| `text-foreground` | `--foreground` | `#F1F5F9` | `#172033` | body text |
| `text-muted-foreground` | `--muted-foreground` | `#94A3B8` | `#5B6B80` ¹ | secondary text |
| `border-border` | `--border` | `#263449` | `#E2E8F0` | dividers, card edges |
| `border-input` | `--input` | `#31425C` | `#D5DDE8` | field edges |
| `bg-primary`, `text-primary` | `--primary` | `#60A5FA` | `#2563EB` | actions, links, focus ring |
| `text-primary-foreground` | | `#080D19` ² | `#FFFFFF` | text on primary |
| `bg-ai`, `text-ai` | `--ai` | `#A78BFA` | `#7C3AED` | AI-generated things only |
| `text-ai-foreground` | | `#080D19` | `#FFFFFF` | text on AI |
| `bg-data`, `text-data` | `--data` | `#22D3EE` | `#0891B2` ³ | charts, data accents |
| `bg-success`, `text-success` | `--success` | `#34D399` | `#059669` ³ | health, OK states |
| `bg-warning` | `--warning` | `#FBBF24` | `#D97706` ³ | warnings |
| `bg-destructive` | `--destructive` | `#F87171` | `#DC2626` | errors, destructive actions |
| `bg-chart-1..5` | `--chart-*` | blue, violet, cyan, green, amber | same hues, light values | Recharts series |

**Ink tokens** (`text-*-ink`) are the same hue darkened in light mode, or lightened in dark mode, for small text on a tint (`bg-*/12`) or on a plain light background:

| Ink | Dark | Light | Light contrast on its 12% tint over the page |
|---|---|---|---|
| `primary-ink` | `#93C5FD` | `#1D4ED8` | 5.35 |
| `ai-ink` | `#C4B5FD` | `#6D28D9` | 5.60 |
| `data-ink` | `#67E8F9` | `#155E75` | 5.97 |
| `success-ink` | `#6EE7B7` | `#065F46` | 6.27 |
| `warning-ink` | `#FCD34D` | `#92400E` | 5.78 |
| `destructive-ink` | `#FCA5A5` | `#B91C1C` | 5.07 |

In dark mode every ink is at least 7.75:1 on its tint over `surface`.

Notes:
1. The brief's light muted `#64748B` measures 4.48:1 on the page and 4.31:1 on elevated, which fails AA. `#5B6B80` measures 4.93 to 5.44.
2. White on `#60A5FA` is 2.54:1, so dark-mode buttons use dark text (7.6:1).
3. These light values are 3.3 to 3.8:1, so they're for icons, charts and large text only. Small text uses the ink token.

**Rules:**
- Blue means an action.
- Violet means AI. Use it for summaries, the briefing, Ask and "why" reasons, and nowhere else.
- Gradients appear only in category artwork (`.cover`) and the logo mark (`.bg-brand`).
- AI-generated blocks use `.ai-block` (a violet left rule and a faint tint) plus a visible "AI-generated" label.

## Typography

- **Font:** Inter Variable, self-hosted (`@fontsource-variable/inter` 5.3.0, imported in `main.tsx`). The latin file is 48 kB, and the browser downloads it alone thanks to `unicode-range`. The fallback stack is the system UI font. The CSP is `font-src 'self'`, so no CDN.
- **OpenType features:** `cv11` (single-storey a) and `ss01` (open digits) on `body`.

| Utility | Size / line height | Use |
|---|---|---|
| `text-2xs` | 11 / 16 | badges, overlines |
| `text-xs` | 12 / 16 | meta (source, time) |
| `text-sm` | 14 / 20 | body in cards, UI |
| `text-md` | 15 / 22.4 | card titles |
| `text-base` | 16 / 24 | article body |
| `text-lg` / `text-xl` | 18, 20 | section titles |
| `text-2xl` | 24 | page titles (`PageHeader`) |
| `text-3xl` / `text-4xl` | 30, 36 | home headline, article headline (desktop) |

Weights: 400 for body, 500 for UI labels, 600 for titles, 700 for headlines. Reading text is at most about 72ch wide.

## Spacing, radius, elevation

- **Spacing:** Tailwind's 4 px scale.
  - Card padding: `p-4`.
  - Panel padding: `p-5`.
  - Gaps between cards: `gap-4`.
  - Gaps between sections: `mb-6` to `mb-8`.
  - Page gutters: 16 px on phones, 24 px from `sm`.
- **Radius** (`--radius` 10 px): `rounded-md` 8 for buttons and inputs inside cards, `rounded-lg` 10 for buttons and fields, `rounded-xl` 14 for cards, `rounded-2xl` 20 for hero and featured blocks, `rounded-full` for pills and search.
- **Elevation:**
  - `shadow-card`: resting cards and fields.
  - `shadow-raised`: hovered cards.
  - `shadow-overlay`: dialogs, tooltips and the drawer.
  
  Dark shadows are deeper because surfaces carry most of the depth.

## Focus and motion

- **Focus:** `focus-visible:ring-2 ring-ring` (2 px primary). Buttons also get a 2 px offset in the page colour. A base-layer fallback draws a 2 px outline on any `a`, `button`, `summary` or `[tabindex]` that doesn't style its own.
- **Motion:** short colour transitions; cards lift 2 px on hover. `motion-reduce` turns the lift and the tooltip fade off.

## Primitives (`src/components/ui/`)

| Component | Variants | Notes |
|---|---|---|
| `Button` | `default` (primary), `ai`, `outline`, `secondary`, `ghost`, `destructive`, `link`; sizes `xs` `sm` `default` `lg` `icon` `icon-xs` `icon-sm` `icon-lg` | `icon` is 44 px below `md` (touch) and 36 px from `md` |
| `Badge` | `neutral`, `primary`, `ai`, `data`, `success`, `warning`, `destructive`, `outline`, `overlay` (on artwork) | `TypeBadge` maps news→primary, research→ai, investment→success, engineering→warning |
| `Card` | | `bg-surface`, `shadow-card`, `rounded-xl` |
| `Input`, `Textarea`, `Select` | | One field style (`fieldClass`). `Select` stays a native `<select>` with a drawn chevron; the OS picker follows `color-scheme` |
| `Tip` | `side="top" \| "bottom"` | CSS-only tooltip (`[data-tip]`), pointer devices only, for elements that already have an `aria-label`. Radix Tooltip was tried and dropped: +17.6 kB gzip in the main bundle |
| Dialog | | Native `<dialog>` (D-036): `bg-surface rounded-2xl shadow-overlay`, blurred backdrop |

Shared pieces in `components/common.tsx`:
- `Skeleton`, `CardSkeleton`, `ListSkeleton`
- `ErrorState` and `EmptyState` (icon in a tinted circle)
- `TypeBadge`, `Quality`, `PageHeader`
- `Cover` (category artwork) and `CardGrid` (container-query columns)

Category icon and hue: `lib/category.ts`.

## Themes

- `light | dark | system`, stored in localStorage (`newsdc-theme`).
- `public/theme-init.js` applies `.dark` before the bundle runs. It's an external file because the CSP is `script-src 'self'`. `lib/theme.tsx` keeps the class in sync after that.
- `color-scheme` is set per theme, so native controls, scrollbars and select pickers match.
- The `theme-color` metas are `#F6F8FC` and `#080D19`.
