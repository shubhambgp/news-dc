# Dev image (Phase 0): Vite dev server. Phase 10 adds the Nginx static production stage.
FROM node:24-alpine

RUN npm install -g pnpm@11.22.0
WORKDIR /app
RUN chown node:node /app
# Non-root (Phase 8, docs/SECURITY.md).
USER node
COPY --chown=node:node package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --chown=node:node . .

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
