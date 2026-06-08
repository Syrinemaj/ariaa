FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the BGE embedding model so the worker starts instantly.
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en')"

COPY . .

CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "-Q", "celery,ingestion,embedding,execution,reporting,maintenance"]