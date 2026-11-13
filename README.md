# ARIA

ARIA transforme un fichier HAR capturé en navigateur en une automatisation
exécutable : ingestion du trafic réseau, normalisation des endpoints,
inférence de schémas, clustering en workflows métier, puis génération de
plans d'exécution pilotés par LLM à partir d'instructions en langage naturel.

## Stack

| Composant | Techno |
|---|---|
| API | FastAPI (Python 3.10+) |
| Tâches asynchrones | Celery + Redis |
| Base de données | PostgreSQL + pgvector (recherche sémantique / RAG) |
| LLM | AWS Bedrock (`amazon.nova-lite-v1:0`, Converse API — voir `app/llm_observability/pricing.py` pour la comparaison de coûts entre modèles Bedrock) |
| Embeddings | Modèle local (`BAAI/bge-small-en`, sentence-transformers) |
| Frontend | React + Vite |
| Observabilité | Prometheus + Grafana |

## Démarrage rapide

```bash
cp .env.example .env
# éditer .env : au minimum AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, POSTGRES_PASSWORD, JWT_SECRET_KEY

docker compose up -d
```

| Service | URL |
|---|---|
| API | http://localhost:8000 (docs interactives : `/docs`) |
| Frontend | http://localhost:5173 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

Les migrations Alembic tournent automatiquement au démarrage de l'API
(`app/db/init_db.py`). Pour lancer une migration manuellement :

```bash
docker compose exec api alembic upgrade head
```

## Configuration

Toutes les variables sont documentées dans `.env.example`. Points clés :

- `AI_PROVIDER` — toujours `bedrock` (seul fournisseur). Voir `app/core/config.py`.
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` — credentials
  Bedrock, résolus classiquement par boto3 (env vars / `~/.aws/credentials` / IAM role).
- `BEDROCK_MODEL` — modèle Bedrock actif (défaut : `amazon.nova-lite-v1:0`).
- `DATABASE_URL`, `REDIS_URL` — dérivent les URLs scoped (broker/backend/app)
  si non définies explicitement.

## Structure du projet

```
app/                  Backend FastAPI — un sous-package par domaine métier
  ai/                   Client LLM (AWS Bedrock)
  ingestion/             Parsing HAR, filtrage bruit
  normalization/         Canonicalisation des endpoints
  schema_inference/      Inférence de schémas request/response
  workflows/              Clustering en workflows métier
  planner/               Génération de plans depuis une instruction
  rag/                    Recherche sémantique (pgvector)
  llm_observability/      Suivi tokens/coûts, comparaison de modèles
  api/                    Routes HTTP
  ...
frontend/             Frontend React
infrastructure/       Provisioning Grafana + config Prometheus
docker/               Dockerfiles (api, worker — dev et prod)
docs/diagrams/        Diagrammes Mermaid (architecture, pipelines)
scripts/               Scripts opérationnels (usage tokens, cleanup, seed)
  dev/                  Outils de développement local (mock API)
tests/                 Tests automatisés (pytest) + fixtures
```

## Tests

```bash
pip install -r requirements-test.txt
pytest
```

## Observabilité — usage & coûts LLM

- `GET /llm/summary` — totaux tokens/coût (aujourd'hui + lifetime)
- `GET /llm/compare-models` — projette l'usage réel sur les autres modèles
  Bedrock disponibles, pour évaluer un changement de modèle
- Dashboards Grafana : `infrastructure/grafana/provisioning/dashboards/`

## Diagrammes

Voir `docs/diagrams/` — architecture système et pipeline d'ingestion HAR
(format Mermaid, visualisable directement sur GitHub ou via l'extension
Mermaid de votre éditeur).
