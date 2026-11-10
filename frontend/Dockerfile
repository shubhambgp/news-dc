# Targets: `dev` (Vite dev server, docker-compose.yml) and the default prod stage
# (static build served by unprivileged Nginx, docker-compose.prod.yml).
FROM node:24-alpine AS dev
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

FROM dev AS build
# Empty = same origin: Caddy serves the app and proxies /api/*.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO /dev/null http://127.0.0.1:8080/ || exit 1
