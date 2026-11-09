# Risks

| ID | Risk | Likelihood / Impact | Mitigation | Owner | Status | Escalate when |
|---|---|---|---|---|---|---|
| R-001 | Docker isn't installed on the agent's build machine, so `docker compose up --build` couldn't run. Compose and Dockerfiles are unverified at runtime. | High / High | Compose validated against the official compose-spec JSON schema. App verified outside Docker against a real Postgres. The human runs the compose check. | Human | Open | Compose fails on the human's machine |
| R-002 | `uv` isn't installed on the machine. The agent used a session-only copy. | High / Low | README links the uv install docs. CI installs uv itself. | Human | Open | Human can't run backend checks locally |
| R-003 | Bleeding-edge tool versions (TypeScript 7, Vite 8, Tailwind 4, shadcn 4) may hit incompatibilities later. | Medium / Medium | Lockfiles committed. Pin or downgrade if a later phase breaks. | Agent | Open | A build or type error traced to tooling |
| R-004 | APScheduler isn't a durable queue (§11.4). | Certain / High if ignored | A DB-backed job table with `SKIP LOCKED` is planned for Phase 3. | Agent | Planned | Phase 3 |
| R-005 | LLM model IDs and capabilities may change. | Medium / Medium | IDs come from env and are verified against official docs in Phase 3/6. | Agent | Open | Phase 3 |
| R-006 | Source volume may not reach 1,500 raw / 500 processed. | Medium / Medium | Report actual counts. Never fabricate (§11.6). | Agent + Human | Open | Phase 2 backfill |
| R-007 | Phase 1 was verified locally on PostgreSQL 18.6 + pgvector 0.8.1, not on the `pgvector/pgvector:pg16` image used by compose and CI. | Medium / Low | Only portable DDL is used (no PG17/18 features). CI runs the integration tests on the pg16 image. | Human | Open | CI integration tests fail |
| R-008 | The startup seed runs in every backend process. A YAML error stops startup. | Low / Medium | YAML is validated in a unit test that runs in CI, so a bad file fails CI first. | Agent | Mitigated | Startup fails after a config edit |
