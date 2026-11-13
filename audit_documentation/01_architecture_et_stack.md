# 01 — Architecture générale et environnement technique

> Racine du dépôt analysé : `C:\aria1.0\aria`. Toutes les références de fichiers ci-dessous sont relatives à cette racine.

## 1. Vue d'ensemble

ARIA est composé de trois processus applicatifs distincts partageant une même base PostgreSQL et un même Redis :

1. une API HTTP FastAPI (`app/main.py`),
2. un ou plusieurs workers Celery exécutant les tâches asynchrones (`app/workers/celery_app.py`),
3. une application frontend React/Vite servie séparément (`frontend/`).

Point d'entrée backend : `app/main.py` (instancie `FastAPI()`, monte les middlewares CORS/rate-limit, inclut les routeurs de `app/api/`).
Point d'entrée frontend : `frontend/src/main.tsx` (non lu en détail dans cet audit — **À VÉRIFIER** le contenu exact, seule son existence et l'arborescence `frontend/src/pages` ont été confirmées).
Point d'entrée worker : `app/workers/celery_app.py`, démarré par les commandes `celery -A app.workers.celery_app worker ...` déclarées dans `docker/worker.Dockerfile` et `docker/worker.prod.Dockerfile`.

## 2. Tableau des composants

| Composant | Technologie | Version (fichier source) | Rôle | Fichier de référence |
| --- | --- | --- | --- | --- |
| API HTTP | FastAPI | 0.111.0 (`requirements.txt`) | Exposition des routes REST, orchestration synchrone des appels IA/RAG | `app/main.py` |
| Serveur ASGI | Uvicorn | 0.30.1 | Serveur de l'API en développement/conteneur | `docker/api.Dockerfile` (**à vérifier** : commande exacte non relue) |
| ORM / accès BD | SQLAlchemy (mode async via `asyncpg`) | 2.0.31 | Modèles de données, requêtes | `app/models/*.py`, `app/db/` |
| SGBD | PostgreSQL + extension pgvector | image `pgvector/pgvector:pg16` (docker-compose) | Stockage relationnel + vecteurs d'embedding | `docker-compose.yml` |
| Migrations | Alembic | 1.13.2 — 26 fichiers de migration recensés | Évolution du schéma | `alembic/versions/` |
| Cache / file de messages | Redis | image `redis:7` (docker-compose) ; client `redis==5.0.7` | Broker et backend Celery (3 index logiques), cache applicatif, rate limiting, disjoncteur | `app/core/config.py` (`REDIS_BROKER_URL`, `REDIS_BACKEND_URL`, `REDIS_APP_URL`) |
| File de tâches asynchrones | Celery | 5.4.0 | Ingestion HAR, embeddings, exécution, nettoyage planifié, reporting | `app/workers/celery_app.py` |
| Fournisseur IA (complétion) | AWS Bedrock — modèle `amazon.nova-lite-v1:0` | boto3 1.43.51 | Toutes les tâches de compréhension/génération par LLM du pipeline | `app/core/config.py` (`BEDROCK_MODEL`), `app/ai/bedrock_client.py` |
| Fournisseur IA (embeddings) | AWS Bedrock — modèle `cohere.embed-multilingual-v3`, 1024 dimensions | boto3 | Indexation et recherche sémantique des endpoints | `app/core/config.py` (`EMBEDDING_PROVIDER`, `BEDROCK_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`) |
| Fournisseur IA (secours local) | sentence-transformers, modèle `BAAI/bge-small-en`, 384 dimensions | `sentence-transformers>=2.7.0`, `torch>=2.0.0` | Alternative sans appel réseau, configurable via `EMBEDDING_PROVIDER=local` — **non celle utilisée par défaut** | `app/core/config.py` (`LOCAL_EMBEDDING_MODEL`) |
| Frontend | React + TypeScript + Vite | react 18.3.1, vite 6.0.1, typescript 5.6.2 | Interface utilisateur SPA | `frontend/package.json` |
| UI / style | TailwindCSS, lucide-react (icônes), recharts (graphiques), mermaid (diagrammes) | tailwindcss 3.4.15, recharts 3.8.1 | Habillage visuel et visualisations | `frontend/package.json` |
| Authentification | python-jose + passlib/bcrypt | python-jose 3.3.0, bcrypt 3.2.2 | JWT + hachage de mot de passe | `app/auth/jwt.py`, `app/auth/password.py` |
| Rate limiting | slowapi (+ Redis) | 0.1.9 | Limitation de débit par route, compteur partagé entre workers | `app/core/rate_limit.py` |
| Observabilité | OpenTelemetry (API/SDK/instrumentation FastAPI, SQLAlchemy, httpx), Prometheus client, structlog | opentelemetry 1.27.0, prometheus-client 0.20.0 | Traces, métriques, logs structurés | `app/core/config.py` (`OTEL_*`, `PROMETHEUS_METRICS_ENABLED`) |
| Monitoring (infra) | Prometheus + Grafana | prom/prometheus:v2.53.0, grafana/grafana:11.1.0 | Tableaux de bord et alerting opérationnel | `docker-compose.yml`, `infrastructure/grafana/` |
| Conteneurisation | Docker / Docker Compose | — | Orchestration locale (`docker-compose.yml`) et prête-pour-prod (`docker-compose.prod.yml`, images poussées vers un registre Azure `ACR_NAME`) | `docker/*.Dockerfile`, `docker-compose*.yml` |
| Déploiement cible (prod) | Azure Container Registry (laissé supposer par `${ACR_NAME}.azurecr.io`) | — | **À VÉRIFIER** : aucune ressource Azure (Bicep/Terraform) n'a été trouvée au-delà de `infrastructure/azure/` dont le contenu n'a pas été audité en détail dans ce document — voir `10_deploiement_et_configuration.md` | `docker-compose.prod.yml`, `infrastructure/azure/` |

## 3. Mécanismes de communication entre composants

- **Frontend → API** : HTTP/JSON via `fetch`/client HTTP du frontend (`frontend/src/api/`) contre l'API FastAPI ; CORS contrôlé par `CORS_ORIGINS` (`app/core/config.py`) et activé dans `app/main.py` via `CORSMiddleware`.
- **API → Workers** : l'API ne communique jamais directement avec un worker ; elle dépose des tâches dans Redis (broker Celery, `REDIS_BROKER_URL`) et consulte le résultat via le backend Celery (`REDIS_BACKEND_URL`) ou via une table de suivi en base (`app/api/jobs.py`).
- **Workers → API** : aucun appel retour synchrone identifié ; le worker écrit son résultat en base de données / dans le backend Celery, lu ensuite par l'API.
- **API/Workers → PostgreSQL** : SQLAlchemy async (`asyncpg`) côté API, à vérifier côté worker (**À VÉRIFIER** si le worker utilise le driver sync `psycopg2-binary` ou le driver async — les deux sont présents dans `requirements.txt`).
- **API/Workers → AWS Bedrock** : client `boto3` dédié (`app/ai/bedrock_client.py`), horodaté et comptabilisé par `app/llm_observability/`.
- **API/Workers → systèmes cibles externes** (l'API RH/SaaS à automatiser) : `httpx` avec transport DNS épinglé (`app/security/pinned_dns_transport.py`) — voir `07_gouvernance_et_securite.md`.

## 4. Topologie des queues Celery (telle que définie dans le code)

`app/workers/celery_app.py` documente 5 files logiques avec une concurrence recommandée différenciée : `ingestion` (2), `embedding` (1, modèle local singleton), `execution` (10, IO-bound), `reporting` (2), `maintenance` (1, tâches cron). **Écart constaté avec le déploiement réel** : `docker-compose.yml` ne lance qu'un unique service `worker`, et `docker/worker.Dockerfile` démarre un seul process Celery écoutant toutes les queues (`-Q celery,ingestion,embedding,execution,reporting,maintenance`) sans respecter la concurrence différenciée par queue documentée dans le commentaire du module ; `docker/worker.prod.Dockerfile` démarre un worker générique (`--concurrency=4`) sans option `-Q` du tout. Aucun service Celery Beat n'est déclaré dans `docker-compose.yml` ni `docker-compose.prod.yml`, alors qu'un `beat_schedule` existe dans le code (voir `06_execution_et_bulk.md` et `11_difficultes_et_limites.md`) — **à clarifier avec le développeur : la tâche planifiée de nettoyage nocturne (`cleanup-expired-files-daily`) s'exécute-t-elle réellement dans le déploiement actuel ?**

## 5. Éléments non confirmés dans cette section

- Contenu exact de `app/main.py` au-delà de CORS/rate-limit (liste complète des middlewares) — **À VÉRIFIER**.
- Démarrage exact d'Uvicorn (nombre de workers, reload) — **NON IDENTIFIÉ DANS LE CODE** dans ce passage de l'audit.
- Présence effective d'un collecteur OTLP opérationnel (`OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` pointe vers un service nommé `otel-collector` qui n'apparaît dans aucun des deux fichiers `docker-compose*.yml` lus) — **à vérifier avec le développeur**.
