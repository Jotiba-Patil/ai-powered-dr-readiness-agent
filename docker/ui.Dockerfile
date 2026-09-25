# syntax=docker/dockerfile:1
# DR Readiness dashboard. Build context: repository root (see docker-compose.yml).

# ---- build: type-check and bundle the React app ----
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty = same origin: nginx below proxies /api to the API container, so no CORS is needed.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ---- runtime: static files behind unprivileged nginx ----
FROM nginxinc/nginx-unprivileged:1.30-alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
