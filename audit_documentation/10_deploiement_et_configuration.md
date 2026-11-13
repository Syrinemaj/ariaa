# 10 — Déploiement et configuration

## 1. Fichiers Docker

- `docker/api.Dockerfile`, `docker/api.prod.Dockerfile` — image API (dev vs prod).
- `docker/worker.Dockerfile`, `docker/worker.prod.Dockerfile` — image worker Celery.
- `docker-compose.yml` — environnement de développement local.
- `docker-compose.prod.yml` — assemblage « prêt pour prod » référencé par la CI, mais **non celui réellement utilisé pour le déploiement cible** : le déploiement réel (`infrastructure/github_actions/deploy.yml`) passe par **Azure Container Apps**, pas par `docker compose up` sur un hôte — `docker-compose.prod.yml` sert vraisemblablement de référence locale pour reproduire la configuration prod, **à confirmer avec le développeur**.

## 2. Services définis dans `docker-compose.yml` (développement)

| Service | Image/Build | Port exposé | Rôle |
| --- | --- | --- | --- |
| `api` | `docker/api.Dockerfile` | 8000 | API FastAPI |
| `worker` | `docker/worker.Dockerfile` | — | Worker Celery (toutes les queues sur un seul process, voir `01_architecture_et_stack.md` §4) |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | Base de données |
| `redis` | `redis:7` | 6379 | Broker/backend Celery, cache, rate limit, disjoncteur |
| `frontend` | `node:20-slim` (dev server Vite) | 5173 | Interface utilisateur |
| `prometheus` | `prom/prometheus:v2.53.0` | 9090 | Collecte de métriques |
| `grafana` | `grafana/grafana:11.1.0` | 3000 | Tableaux de bord |

Volumes nommés : `aria10_postgres_data`, `aria10_prometheus_data`, `aria10_grafana_data`. Montage bind de tout le dépôt dans `api`/`worker` (`./:/app`) — cohérent avec un usage de développement (rechargement à chaud), pas avec une image figée.

## 3. `docker-compose.prod.yml`

Services réduits à `api`, `worker`, `postgres`, `redis` (pas de `frontend`/`prometheus`/`grafana` dans ce fichier). Images tirées d'un registre Azure (`${ACR_NAME}.azurecr.io/aria-api:${IMAGE_TAG:-latest}`), `restart: always`. **Absence confirmée** : aucun service `celery beat` (voir `06_execution_et_bulk.md` §8), aucun port exposé explicitement pour `postgres`/`redis` (cohérent avec un réseau interne Azure plutôt qu'un accès direct depuis l'hôte).

## 4. CI/CD

`infrastructure/github_actions/deploy.yml`, déclenché sur push vers `main` :
1. Connexion Azure (`azure/login@v1`), connexion à l'ACR.
2. Build + push des deux images (API, Worker) vers `$ACR_NAME.azurecr.io`, taguées à la fois par le SHA du commit et `latest`.
3. Mise à jour de deux Azure Container Apps (`aria-api`, `aria-worker`) via `az containerapp update`.
4. Vérification de santé : `curl --fail https://$API_URL/health` sur l'URL FQDN de l'app.

**Constat vérifié directement dans le fichier** : **aucune étape d'exécution de tests ou de lint n'est présente dans ce workflow avant le build/déploiement** — le pipeline déploie directement sur push vers `main`, sans porte de qualité automatisée. C'est un point IMPORTANT à signaler (absence de gate CI, pas un bug en soi, mais une caractéristique réelle du déploiement actuel).

## 5. Variables d'environnement (noms uniquement, conformément à la règle de confidentialité)

Lues depuis `app/core/config.py` (`class Settings(BaseSettings)`, `env_file = ".env"`) :

`DATABASE_URL`, `REDIS_URL` (+ `REDIS_BROKER_URL`/`REDIS_BACKEND_URL`/`REDIS_APP_URL` dérivées), `EMBEDDING_PROVIDER`, `BEDROCK_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `LOCAL_EMBEDDING_MODEL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `CONNECTION_ENCRYPTION_KEY`, `CORS_ORIGINS`, `DEFAULT_ORG_NAME`, `BULK_FILE_MAX_SIZE_MB`, `BULK_MAX_ROWS`, `BULK_BATCH_SIZE`, `BULK_RATE_LIMIT_PER_SECOND`, `BULK_STEP_RETRIES`, `ALLOWED_TARGET_DOMAINS`, `ALLOW_HTTP_TARGETS`, `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_AUTH`, `RATE_LIMIT_UPLOAD`, `RATE_LIMIT_EXECUTE`, `LLM_PROMPT_COST_PER_1K`, `LLM_COMPLETION_COST_PER_1K`, `LLM_HIGH_TOKEN_THRESHOLD`, `LLM_MAX_COMPLETION_TOKENS`, `LLM_MAX_INPUT_TOKENS`, `LLM_MAX_INPUT_CHARS`, `LLM_STRUCTURED_TEMPERATURE`, `PLAN_MIN_INTENT_CONFIDENCE`, `PLAN_MIN_RAG_SCORE`, `UPLOAD_DIR`, `UPLOAD_FILE_TTL_DAYS`, `UPLOAD_FAILED_FILE_TTL_HOURS`, `CLEANUP_DRY_RUN`, `AI_PROVIDER`, `AWS_REGION`, `BEDROCK_MODEL`, `OTEL_ENABLED`, `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `PROMETHEUS_METRICS_ENABLED`, `AWS_COST_SYNC_ENABLED`, `AWS_COST_SYNC_INTERVAL_SECONDS`, `METRICS_ALLOWED_IPS`, `METRICS_BEARER_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`, `FRONTEND_URL`, `PASSWORD_RESET_TTL_SECONDS`.

Plus, hors de `config.py`, utilisées directement par `docker-compose.yml` : `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` ; par la CI : `ACR_NAME`, `AZURE_CREDENTIALS` (secrets GitHub Actions).

## 6. Nginx

**NON IDENTIFIÉ DANS LE CODE.** Aucun fichier de configuration Nginx n'a été localisé dans ce passage d'audit (ni `nginx.conf`, ni service `nginx` dans l'un des deux `docker-compose*.yml`, ni dossier `infrastructure/nginx/`). Le trafic HTTP semble géré directement par l'ingress des Azure Container Apps en production. **À confirmer avec le développeur si un reverse proxy existe ailleurs dans l'infrastructure réelle, hors de ce dépôt.**

## 7. Monitoring

Prometheus + Grafana définis uniquement dans `docker-compose.yml` (développement), avec provisioning versionné (`infrastructure/grafana/provisioning/`). **Absents de `docker-compose.prod.yml`** — l'observabilité en production semble donc reposer sur un autre mécanisme (Azure Monitor ? un Prometheus managé séparément ?), **non identifié dans ce dépôt**. Le endpoint `/metrics` de l'API est protégé par IP whitelist ou jeton Bearer (`METRICS_ALLOWED_IPS`, `METRICS_BEARER_TOKEN`), confirmé dans `app/core/config.py`.

## 8. Migrations

Alembic, 26 fichiers sous `alembic/versions/`. Mécanisme de déclenchement en déploiement (étape manuelle vs automatisée dans la CI) — **NON IDENTIFIÉ** dans `infrastructure/github_actions/deploy.yml` : aucune étape `alembic upgrade head` n'apparaît dans ce workflow. **À vérifier avec le développeur** : les migrations sont-elles appliquées manuellement, via une étape de démarrage du conteneur (`CMD` du Dockerfile, non vérifié en détail dans ce passage), ou par un mécanisme distinct ?

## 9. Dépendances entre services (ordre de démarrage)

`docker-compose.yml` déclare `depends_on` pour `api`/`worker` → `postgres`, `redis` ; `frontend` → `api` ; `prometheus` → `api` ; `grafana` → `prometheus`. Il s'agit d'un ordre de démarrage de conteneur (pas d'attente active de disponibilité du service — Compose ne garantit pas que `postgres` accepte déjà des connexions quand `api` démarre, sauf `healthcheck` explicite, **absent** des définitions de service relues dans ce passage).
