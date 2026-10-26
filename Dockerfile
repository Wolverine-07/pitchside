# One image: the React broadcast view is built, then served by the FastAPI app.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app/backend
RUN pip install --no-cache-dir uv==0.13.1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN uv sync --frozen --no-dev
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/uvicorn pitchside.api:app --host 0.0.0.0 --port ${PORT}"]
