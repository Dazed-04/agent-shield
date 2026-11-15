# ---- Stage 1: build the React frontend -------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: runtime ---------------------------------------------------------------
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf-cache \
    SECURITY_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (saves ~2 GB), then the rest (cached unless requirements change)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image: no runtime download, works offline.
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2')"

COPY backend/app/ ./app/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Run unprivileged; only /app/sandbox and /app/data are writable.
RUN useradd --system --uid 10001 shield \
    && mkdir -p /app/sandbox /app/data \
    && chown -R shield:shield /app/sandbox /app/data /opt/hf-cache
USER shield

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://localhost:8000/api/models || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
