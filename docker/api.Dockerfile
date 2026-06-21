# ── Stage 1 : Build React frontend ───────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── Stage 2 : Python FastAPI + static files ───────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model for air-gapped / instant startup
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en')"

COPY . .

# Copy the built React app → FastAPI serves it from /app/static
COPY --from=frontend-builder /frontend/dist ./static

CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed_users && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
