# One image, one dyno: Next.js serves the site on $PORT and forwards /api to FastAPI on 127.0.0.1:8010.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Rewrites are fixed at build time: the API runs beside Next in the same container.
ENV BACKEND_URL=http://127.0.0.1:8010 NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM python:3.12-slim
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
COPY backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY rules/ rules/
COPY --from=web /web/.next/standalone web/
COPY --from=web /web/.next/static web/.next/static
COPY --from=web /web/public web/public
COPY start.sh ./
CMD ["bash", "start.sh"]
