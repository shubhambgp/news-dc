# Security

How NewsDC handles secrets, input, output, admin access and deployment (PLAN Phase 8 step 3, §11.6, §11.9). Each control names where it lives and what tests it. "Phase 9/10" marks controls that belong to parts not built yet.

## Secrets

- Every secret comes from the environment or a local `.env` (`app/config.py`). `.env` and `.env.*` are gitignored; only `.env.example` (empty values) is committed.
- Secrets: `ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, `SESSION_SECRET`, `GITHUB_TOKEN`, `POSTGRES_PASSWORD`.
- No secret reaches the frontend. The only build-time frontend variable is `VITE_API_BASE_URL`. The browser never calls Anthropic: answers come from `/api/v1/ask`.
- `SESSION_SECRET` signs admin cookies and is never the admin token (§11.9). Admin stays disabled unless `ADMIN_TOKEN` is ≥ 16 characters and `SESSION_SECRET` ≥ 32.
- Logs never contain secrets, request bodies, query strings, full prompts or article text. The access log records the path only. Ask NewsDC logs counts, tokens and cost, never the question. Failed admin logins log the client IP only.

### Rotating a secret

| Secret | Steps | Effect |
|---|---|---|
| `ADMIN_TOKEN` | Generate (`python -c "import secrets; print(secrets.token_urlsafe(32))"`), set it in `.env`, restart `backend` | Old token stops working. Existing sessions stay valid until they expire (≤ `ADMIN_SESSION_MINUTES`); rotate `SESSION_SECRET` too to end them now |
| `SESSION_SECRET` | Generate a new ≥ 32-char value, set it, restart `backend` | Every admin session ends at once |
| `ANTHROPIC_API_KEY` | Create a new key in the Anthropic console, set it, restart `backend` and `worker`, then revoke the old key | No downtime beyond the restart |
| `GITHUB_TOKEN` | Same pattern: new token, restart `worker`, revoke the old one | |
| `POSTGRES_PASSWORD` | `ALTER USER newsdc PASSWORD '...'`, update `.env`, restart `backend` and `worker` | |

The Anthropic key that was pasted into a chat during Phase 3 was rotated by the human (2026-11-11).

## Admin access

`app/api/admin.py`, `app/security.py`; contract in `docs/API.md#admin`; decisions in D-035.

- `POST /api/v1/admin/login` compares the token with `hmac.compare_digest` and gives no hint about partial matches.
- On success it sets `newsdc_admin`: `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/admin`, expiring after `ADMIN_SESSION_MINUTES` (30). The value is an HMAC-SHA256-signed `{sid, csrf, exp}`. Tampered, expired, forged or logged-out cookies are refused.
- Session rotation: every login gets a new session ID and CSRF token. Logout revokes the session and clears the cookie.
- CSRF: `SameSite=Strict`, plus the per-session token in `X-CSRF-Token` on every `POST`/`PATCH`, plus an Origin/Referer allow-list (own origin and `CORS_ORIGINS`).
- Login rate limits: 5/minute per IP, 30/minute for all clients together. One client can't lock everyone out.
- Every other `/admin/*` route returns 401 without a valid session.
- Admin actions queue jobs. The API process never runs ingestion or LLM calls for admin.
- Tests: `tests/test_admin.py` (auth, cookie flags, rate limits, CSRF, origin, logout, rotation, forged/expired cookies, disabled mode) and `tests/test_admin_db.py` (every action).

## Input validation and limits

- Pydantic validates every body, path and query parameter. Request models reject unknown fields. Errors use the standard envelope, and messages name the field without echoing the value.
- Request bodies: `Content-Length` required (411) and at most 64 KiB (413), `app/main.py:body_limit`.
- For You profile: ≤ 200 read IDs, ≤ 100 tags, ≤ 64 categories, ≤ 500 bookmarks and dismissals, numeric bounds on weights, existing category slugs only (`schemas.Profile`).
- Ask: question 3–500 characters, history ≤ 4 messages of ≤ 4,000 characters. Admin: token ≤ 512, category name ≤ 80, description ≤ 500, ≤ 50 keywords.
- Pagination: `page_size` ≤ 50, `page` ≤ 1000, export `limit` ≤ 1000.
- SQL goes only through SQLAlchemy expressions with bound parameters. No SQL is built from strings with user input; a grep for f-string `text()` and `.format` SQL in `app/` finds none.

## Rate limits

`app/security.py`, in-process (R-017, R-018): 60/minute per IP on every route except `/health` and `/ready`, 10/minute per IP for `/ask` plus 30/minute and 500/day for all clients together (`RATE_LIMIT_ASK_GLOBAL`, the ceiling on Ask spend), and the login limits above. IPv6 clients are keyed by /64. At most 8 Ask answers stream at once (D-040). Tests in `tests/test_api.py` and `tests/test_admin.py`.

## Untrusted content

- Source content is untrusted. Ingestion strips scripts and markup (`html_to_text`) and never executes embedded content.
- SSRF (`app/ingest/common.py:Http`): only `http(s)` URLs, and every redirect hop's resolved address must be public (no loopback, private, link-local, multicast, NAT64). The connection goes to the checked address, so DNS rebinding can't swap it (D-040). Each request has a 60 s deadline, and `Authorization` is never sent to another host on redirect. Redirects are bounded, plus size caps and timeouts. Tests in `tests/test_ingest_common.py`.
- Paywalls and robots.txt are respected (D-016). Full text is stored only where the source allows it, and it is never returned by the API or exported.
- LLM output is untrusted. Ask NewsDC citations are built from retrieved item IDs and DB URLs, and unknown `[n]` are removed (§11.8). Retrieved text is fenced as evidence, never instructions.
- API search snippets are HTML-escaped, with only `<mark>` added. The Markdown export escapes every markup character and links only `http(s)` URLs.
- Frontend (Phase 9): model Markdown (answers, trend brief) goes through `react-markdown` with `skipHtml`, images dropped, and no links except `[n]` citations: a link the model writes is shown as text (`frontend/src/components/Markdown.tsx`). Summaries and titles are plain React text. Every external `href` passes `safeUrl` (`http`/`https` only) and opens with `rel="noopener noreferrer"`. Search snippets are split on `<mark>` and decoded as text, never set with `innerHTML`. The admin CSRF token lives only in memory (TanStack Query cache), never in `localStorage`. The E2E test checks that an escaped snippet renders as text.

## Headers, CORS, CSP

- Every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Request-ID`. API responses: `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`. The Swagger page is left without CSP rather than given a policy that breaks it, and it is turned off in production (`API_DOCS=false`), where it would load a CDN script on the admin's origin.
- CORS: only `CORS_ORIGINS`, with credentials (admin cookie), methods `GET`/`POST`/`PATCH`, headers `Content-Type`, `X-Request-ID`, `X-CSRF-Token`. In production the frontend and API share one origin behind Caddy, so `CORS_ORIGINS` is the site itself.
- Frontend CSP set by Caddy (D-037): `default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `connect-src 'self'`, `frame-ancestors 'none'`, plus HSTS. The live app works under it (human click-through, 2026-11-11).

## Deployment

- Containers run as non-root: backend uid 10001 (`backend/Dockerfile`), frontend dev image as `node` (`frontend/Dockerfile`). Not built on the agent machine because Docker isn't available (R-001).
- The dev database port is bound to `127.0.0.1` only. The production database has no published port; only Caddy publishes 80/443 (`ufw` allows SSH, 80, 443).
- Encrypted database backups (`0600`, restore tested, docs/DEPLOYMENT.md); `pip-audit` and `pnpm audit` in CI (no container image scanner, D-037); uvicorn trusts proxy headers only from the compose network, so rate limits see client IPs. Secret rotation: docs/DEPLOYMENT.md.

## Audit 2026-11-10

Triage of `security-audit/` (audited `8b4c0f0`) after checking each finding against the code. Fixes are in D-040.

| Outcome | Findings |
|---|---|
| Fixed in code | NDC-01 global Ask limit · NDC-02 pinned connections · NDC-05 stream cap · NDC-06 IPv6 /64 · NDC-07 model links as text · NDC-08 sessions end on restart · NDC-13 fetch deadline · NDC-15 docs off in prod · NDC-16 control characters · NDC-17 token on redirect · NDC-19 NAT64 · NDC-22 restore passphrase · NDC-10 `cap_drop` (partly) · NDC-24 Caddy/Nginx bump and pull on deploy (partly) |
| Human action, no code (done 2026-11-11) | NDC-04 rotate the Anthropic key · NDC-01 set a spend limit in the Anthropic console · NDC-12 branch protection and environment reviewers · NDC-20 confirm `PasswordAuthentication no` |
| Accepted or overstated | NDC-03: prompt injection can't be fixed in code. Spam is already rejected by `gate()`, so the audit's "drop summaries of spam" is already done; an adversarial eval needs paid calls. NDC-14: an HN poster already chooses their own link and title, so a redirect adds only the merge of a later duplicate. NDC-18: the global login cap is the brute-force defence, and exempting correct tokens would remove it; the CLI on the server still works. NDC-21: logged, and the per-run item cap still applies. NDC-23: dev-only, not in the bundle. NDC-09 (database superuser), NDC-11 (SHA pinning) and the CI Trivy gate are worth doing but need a server migration or a policy decision. |
