# Inventaire factuel du code — préalable à la rédaction du chapitre Conception

> Racine du dépôt applicatif : `C:\aria1.0\aria`. Ce document précède et fonde `chapitre_conception.tex` ; il réutilise et complète les constats de l'audit antérieur (`audit_documentation/`), revérifiés ici pour les besoins précis de la Conception (schémas, algorithmes, structures de données). Toute affirmation est sourcée par chemin de fichier.

## 1. Structure globale

Trois processus applicatifs partageant PostgreSQL + Redis : API FastAPI (`app/main.py`), worker(s) Celery (`app/workers/celery_app.py`), frontend React/Vite (`frontend/`). En production, le frontend est **construit statiquement et servi par l'API elle-même** : `app/main.py` lignes 218-238 monte `StaticFiles` sur `app/static/` avec un fallback SPA (`spa_fallback`) — ce n'est donc pas un service séparé en production, contrairement au développement (`docker-compose.yml` démarre un service `frontend` Vite distinct, port 5173). `docker-compose.yml` (dev, 7 services) / `docker-compose.prod.yml` (4 services : api, worker, postgres, redis). CI/CD : `.github/workflows/ci.yml` + `infrastructure/github_actions/deploy.yml` (déploiement réel vers Azure Container Apps). `infrastructure/azure/deploy_azure_cli.md` (guide manuel, partiellement obsolète — référence encore `AZURE_OPENAI_*`, fournisseur IA abandonné depuis le passage à Bedrock, voir §11).

## 2. Backend FastAPI — routeurs et couches

`app/main.py` inclut 17 routeurs (`app/api/*.py`) : `auth`, `users`, `teams`, `upload`, `registry`, `openapi`, `rag`, `automation`, `reports`, `bulk`, `approvals`, `audit`, `governance`, `connections`, `maintenance`, `notifications`, `jobs`, `llm` — 98 routes au total (comptage `grep '@router\.'`, voir `audit_documentation/08_base_de_donnees_et_api.md`).

Couches réelles : `app/api/*.py` (routeurs, dépendances FastAPI) → modules de service par domaine (`app/automation/service.py`, `app/bulk_execution/service.py`, `app/connections/service.py`, `app/governance/*.py`, etc. — pas un dossier `services/` unique mais un découpage par domaine métier) → `app/models/*.py` (SQLAlchemy ORM) ; schémas Pydantic dans `app/schemas/` et localement à chaque routeur. Pas de couche `repository` explicite nommée : les services accèdent directement à SQLAlchemy.

Middlewares réels, dans l'ordre d'ajout (`app/main.py`) : `CORSMiddleware` → télémétrie OpenTelemetry (`setup_telemetry`) → middleware fonction `add_request_id` (corrélation `X-Request-ID` + `ContextVar`) → middleware fonction `metrics_guard` (protège `/metrics` par IP whitelist ou jeton Bearer) → `MetricsMiddleware` (Prometheus) → `SlowAPIMiddleware` (rate limiting). Gestion d'erreurs : handler dédié pour `RateLimitExceeded` ; sinon exceptions FastAPI standard (`HTTPException`).

Dépendances d'injection confirmées (`app/auth/dependencies.py`) : `get_current_user` (décode JWT, vérifie liste de révocation JTI dans Redis, vérifie une version de token pour invalidation en masse, cache l'utilisateur 60 s dans Redis via `ARIACache`), `require_roles(allowed_roles)`, `require_admin`, `require_admin_or_operator`.

## 3. Workers Celery

`app/workers/celery_app.py` : 5 queues **conçues** avec concurrence différenciée — `ingestion` (4 workers × concurrency 2), `embedding` (2 × 1, singleton sentence-transformers), `execution` (8 × 10, IO-bound), `reporting` (2 × 2), `maintenance` (1 × 1, cron). Commandes de démarrage documentées littéralement en commentaire d'en-tête, un process par queue + un process `beat`. `task_acks_late=True`, `task_reject_on_worker_lost=True`, `worker_prefetch_multiplier=1`, `result_expires=3600`, sérialisation JSON. `beat_schedule` réel : `cleanup-expired-files-daily` (tous les jours 2h UTC → `app/workers/tasks/cleanup.py::cleanup_expired_files`). Écart avec le déploiement effectif (un seul worker générique, pas de `beat`) : voir `audit_documentation/01_architecture_et_stack.md` §4 — relève du chapitre Réalisation, mentionné ici seulement comme limite de déploiement, pas de conception.

## 4. Modèle de données

SQLAlchemy 2.0.31, driver `asyncpg` (API) — 27 tables (`app/models/*.py`), 26 migrations Alembic (`alembic/versions/`). Table vectorielle : `endpoint_embeddings` (`app/models/embedding.py`) — colonne `embedding` de type `Vector(EMBEDDING_DIMENSIONS)` (pgvector), **index HNSW** déclaré au niveau ORM (`Index("idx_endpoint_embeddings_hnsw", "embedding", postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"})`), créé avec `CONCURRENTLY` en migration (évite un verrou de table). Mesure de distance : cosinus (`vector_cosine_ops`), cohérent avec `EndpointEmbedding.embedding.cosine_distance(...)` utilisé par `app/rag/retriever.py`.

Tables principales et rôles : voir tableau détaillé dans `audit_documentation/08_base_de_donnees_et_api.md` §2 (repris et cité directement dans le chapitre, §5.1).

États réels observés par grep direct (pas des `Enum` déclarés en base — ces colonnes `status` sont de simples `String`, les valeurs listées ci-dessous sont celles effectivement assignées dans le code) :
- `AutomationRun.status` : `"created"` (défaut) → `"pending_approval"` (si gouvernance l'exige, `app/api/automation.py:465`, `app/api/bulk.py:153`) → `"running"` (`app/automation/service.py:37`, `app/bulk_execution/service.py:110`) → `"success"` / `"partial_success"` / `"failed"` / `"cancelled"` (dérivation finale, `app/workers/tasks/reporting.py:91-95`, corrigée pour distinguer explicitement un échec total ou une annulation d'un succès partiel — voir §11).
- `AutomationApproval.status` : `"pending"` (défaut) → `"approved"` (`app/approval/approval_service.py:41`) / `"rejected"` (`app/api/approvals.py:179`).
- `BulkBatch.status` : `"running"` → `"completed"` / `"cancelled"` (`app/bulk_execution/batch_executor.py:371`).
- `DataRow.status` : `"invalid"` / `"valid"` / `"success"` / `"failed"` (cascade de validation puis d'exécution bulk).

## 5. Frontend React

Voir `audit_documentation/02_frontend_et_parcours.md` (repris sans reformulation d'audit) : `frontend/src/{pages,components,contexts,lib,hooks,types}`, point d'entrée `main.tsx` → `App.tsx` (providers `ThemeProvider > AuthProvider > RunProvider > ToastProvider`, React Router v6, `ErrorBoundary`). Authentification : `contexts/AuthContext.tsx`, jetons en `sessionStorage` (isolement par onglet, commenté explicitement dans le code). RBAC côté client : `components/layout/RequireRole.tsx`, doublé côté serveur par les dépendances FastAPI (§2).

## 6. Module IA — détail par étape (noms de fichiers/fonctions confirmés par lecture directe)

- **Parsing HAR** : `app/ingestion/har_parser.py::parse_har_file` → liste de `TrafficEntry`.
- **Filtrage dur** : `app/ingestion/traffic_cleaner.py::clean_traffic`.
- **Score heuristique** (formule exacte, lue dans `app/ingestion/heuristic_filter.py::compute_heuristic_score`) :
  `score = 0.25·[method∈{POST,PUT,PATCH,DELETE}] + 0.05·[method=GET] + 0.25·has_structured_content + 0.15·has_api_hint + 0.10·[200≤status<400]`, plafonné à 1.0. Poids recalibrés empiriquement (docstring : 0.643→0.667 précision, 0.783→0.800 F1, sur `evaluation/golden_dataset/traffic_classification_golden_dataset.json`) — **résultat expérimental, à ne pas répéter dans le chapitre Conception** (relève du chapitre Évaluation), seule la formule/structure est pertinente ici.
- **Score payload** : `app/ingestion/payload_classifier.py::compute_payload_score`, ~40 mots-clés métier FR/EN.
- **Seuils** : `app/ingestion/noise_scoring.py` — `LOW_THRESHOLD=0.30`, `HIGH_THRESHOLD=0.70`.
- **Arbitrage IA zone grise** : `app/ingestion/semantic_filter.py`, modèle `amazon.nova-lite-v1:0`.
- **Normalisation URL** : cascade motifs (`app/normalization/parameter_detector.py`) → statistique inter-requêtes par point fixe (`app/normalization/dynamic_segment_detector.py`) → regroupement LLM (`app/normalization/group_normalizer.py`, seuil confiance 0.70).
- **Enrichissement endpoint** : `app/ai/endpoint_understanding.py::enrich_endpoint_with_ai`.
- **Embeddings** : `cohere.embed-multilingual-v3` (Bedrock), 1024 dim, texte construit par `app/rag/embeddings/builder.py::build_endpoint_embedding_text`.
- **Recherche sémantique** : `app/rag/retriever.py::semantic_search_endpoints`, `top_k=5`, `score_threshold=0.35` (défaut Pydantic `SemanticSearchRequest`), distance cosinus pgvector, embedding asymétrique (`search_document`/`search_query`).
- **Jugement de pertinence** : `app/rag/relevance_judge.py::verify_relevance_async`, systématique, retourne `relevant` + `missing_aspects`.
- **Analyse d'intention** : `app/planner/intent_analyzer.py::analyze_business_intent`, échelle de confiance 0.0–1.0 (4 paliers documentés dans le prompt), seuil de rejet `PLAN_MIN_INTENT_CONFIDENCE=0.4`.
- **Génération de plan** : `app/planner/plan_builder.py::build_automation_plan` + `app/planner/plan_generator.py::generate_plan_selection` (sélection ancrée dans le RAG, filtrage anti-hallucination en code).
- **Schéma du plan** (Pydantic, `app/planner/models.py`) : `AutomationPlan{run_id, instruction, intent: BusinessIntent, workflow_name, steps: [PlanStep], requires_approval, dry_run_default=True, metadata}` ; `PlanStep{order, endpoint_id, method, path, canonical_key, action, business_domain, depends_on: [str], request_schema, response_schema, auth_required, risk_level, field_mapping}`.
- **Dépendances et tri topologique** : `app/planner/step_ordering.py` — `detect_schema_dependencies` (un step POST/PUT produisant un champ `id`/`*_id` dans son `response_schema` devient dépendance de tout step ultérieur dont un segment `{param}` porte ce nom) + `topological_sort_steps` (Kahn, tri stable par ordre d'entrée, lève `DependencyCycleError` si cycle). Utilisé par `plan_builder.py`, `plan_validator.py`, et `app/api/automation.py::plan_from_workflow`.
- **Validation du plan** : `app/planner/plan_validator.py` — appelle `topological_sort_steps` (détection de cycle) et produit des `PlanValidationIssue` (dont la référence à un `canonical_key` absent de l'ensemble RAG réellement récupéré, non levée comme exception silencieuse).
- **Clustering de workflows** : `app/workflows/clustering.py` — règles fixes (transverse) + cascade LLM principal / préfixe commun / DBSCAN. **Mécanisme réel d'ordonnancement des étapes d'un workflow détecté : `app/workflows/sequence_builder.py::reorder_steps_sync`, appelé littéralement en `clustering.py:459`.** `app/workflows/dag_builder.py::WorkflowDAG` et `app/workflows/dag_executor.py::execute_dag` existent et modélisent une exécution parallèle par lots indépendants (Kahn + `asyncio.gather`), mais **aucun appelant n'a été trouvé dans tout le dépôt** (`grep -rl "execute_dag"` ne retourne que sa définition et un commentaire de `dag_builder.py`) — composant conçu mais non branché en production. Ce point est traité explicitement en §6.8/Limites du chapitre, pas présenté comme le mécanisme réel.

## 7. Sécurité

JWT `HS256` (`python-jose`), access 30 min / refresh 30 jours, secret validé ≥32 octets au démarrage. Rôles : `ADMIN`/`OPERATOR` uniquement (`app/models/user.py::UserRole`, un rôle `VIEWER` existait et a été retiré en migration 014). Bcrypt (`passlib`). SSRF : `app/security/ssrf_guard.py` + `app/security/pinned_dns_transport.py` (validation puis épinglage DNS). Secrets de connexion : Fernet (`app/connections/crypto.py`), déchiffrement uniquement côté worker. Rate limiting : `slowapi` + Redis partagé, 4 limites nommées (`RATE_LIMIT_DEFAULT/AUTH/UPLOAD/EXECUTE`). CORS : liste blanche `CORS_ORIGINS`. Anti-traversée de chemin + validation de cohérence d'hôte : `app/automation/executor.py`.

## 8. Gouvernance

`app/governance/policy_engine.py::check_execution_policy(plan, policy, forbidden_rules, environment) -> PolicyResult`. Algorithme exact (lu intégralement) :
1. `_check_forbidden_rules` : toute étape dont (méthode, motif `fnmatch` du chemin) correspond à une `ForbiddenEndpointRule` → `BLOCK` immédiat.
2. `_check_environment_policy` : pas de politique configurée pour l'environnement → `BLOCK` ("failing closed") ; mode `forbidden` → `BLOCK` ; mode `full_access` → `ALLOW` ; mode `read_only` avec étapes d'écriture → `BLOCK` ; mode `writes_require_approval` avec étapes d'écriture → `REQUIRE_APPROVAL` ; mode inconnu → `BLOCK` ("failing closed").
3. `_check_risk_threshold(risk_score, low, high)` : `risk_score ≤ low` → `ALLOW` ; `risk_score > high` → `BLOCK` ; sinon `REQUIRE_APPROVAL`.
La décision finale retenue est la plus sévère des trois (`_SEVERITY = {ALLOW:0, REQUIRE_APPROVAL:1, BLOCK:2}`), avec la garantie explicite qu'un `BLOCK` ne peut jamais être rétrogradé.

`app/governance/scoring.py::compute_plan_risk_score(plan) = max(step_risk_score(s.risk_level) for s in plan.steps)`, barème `{"low":1,"medium":5,"high":10}`, valeur inconnue → traitée comme `"high"` ("fails closed"). `PlanStep.risk_level` vient de `app/planner/plan_builder.py::_risk_level(method, quantity)`.

Points d'appel confirmés (double évaluation, submission + exécution réelle) : `app/api/automation.py:402` (soumission simple), `app/api/bulk.py:96` (soumission bulk), `app/workers/tasks/execution.py:277` (juste avant l'exécution réelle, dans le worker). Règle bulk spécifique (`app/api/bulk.py::_resolve_bulk_governance_and_approval`) : `needs_approval = policy_result.decision == REQUIRE_APPROVAL or current_user.role != ADMIN` — un opérateur a **toujours** besoin d'une approbation admin pour un bulk réel.

Politique par défaut (`app/models/governance.py::DEFAULT_ENVIRONMENT_POLICIES`) : `{"test":"full_access","preprod":"full_access","prod":"full_access"}` — les trois environnements démarrent en accès complet.

## 9. Exécution

Simulation systématique avant exécution réelle (`app/dry_run/simulator.py`). Garde d'approbation : `app/approval/approval_guard.py::assert_approval_for_real_execution`. Résolution de paramètres de chemin, anti-traversée (`%252e`/`%252f` doublement encodés), validation de cohérence d'hôte : `app/automation/executor.py`. Bulk : limites `BULK_FILE_MAX_SIZE_MB=20`, `BULK_MAX_ROWS=10000`, lots de `BULK_BATCH_SIZE=50`, limite de débit Redis `BULK_RATE_LIMIT_PER_SECOND=10.0`, retries `BULK_STEP_RETRIES=3`. Disjoncteur `app/resilience/circuit_breaker.py::RedisCircuitBreaker` (`failure_threshold=5`, `recovery_timeout=60s`, `half_open_max_calls=3`, par endpoint, état partagé Redis). Idempotence : `app/idempotency/key_generator.py` (hachage des seuls champs métier stables, pas la ligne complète). Résolution de conflit 409 : `app/bulk_execution/conflict_resolution.py::find_existing_record`.

## 10. Supervision

OpenTelemetry (API/SDK/instrumentation FastAPI, SQLAlchemy, httpx) — `app/core/telemetry.py::setup_telemetry`. Prometheus client + endpoint `/metrics` protégé (IP whitelist ou Bearer). `docker-compose.yml` (dev uniquement) : Prometheus (`prom/prometheus:v2.53.0`) + Grafana (`grafana/grafana:11.1.0`), provisioning versionné (`infrastructure/grafana/provisioning/`, `infrastructure/prometheus.yml`). Absents de `docker-compose.prod.yml` — non spécifié comment la supervision est assurée en production réelle (hors périmètre du dépôt).

## 11. Versions et écarts à noter pour la Conception

Backend (`requirements.txt`) : FastAPI 0.111.0, SQLAlchemy 2.0.31, Alembic 1.13.2, Celery 5.4.0, Redis client 5.0.7, boto3 1.43.51, pgvector 0.2.5, python-jose 3.3.0, passlib/bcrypt, slowapi 0.1.9. Frontend (`package.json`) : React 18.3.1, Vite 6.0.1, TypeScript 5.6.2, TailwindCSS 3.4.15, react-router-dom 6.28.0, recharts 3.8.1, mermaid 11.14.0.

**Écart à traiter en Conception §3 (choix technologiques), pas en Réalisation** : le guide `infrastructure/azure/deploy_azure_cli.md` provisionne encore des variables `AZURE_OPENAI_*` (fournisseur IA historique). Le code de production (`app/core/config.py::AI_PROVIDER`, `app/ai/bedrock_client.py`) n'utilise plus qu'AWS Bedrock — `AzureOpenAIClient` et `GroqClient` ont existé puis ont été retirés après une évaluation comparative chiffrée (`evaluation/results/full_comparison.csv`, résultats = chapitre Évaluation, pas ici). Le guide de déploiement manuel n'a pas été mis à jour après ce changement — à signaler comme limite de conception/documentation, pas comme fonctionnalité du système lui-même.

## 12. Squelette LaTeX du rapport

**NON TROUVÉ** dans `C:\aria1.0` ni `C:\aria1.0\aria` : aucun `main.tex`, aucun `.cls`/`.sty`, aucun dossier `latex/` (recherche `find . -iname "*.tex" -o -iname "*.cls" -o -iname "*.sty"`, résultat vide). Le rapport existant (`rapport/*.md`) est en Markdown, pas en LaTeX. Les macros demandées par la mission (`\reportimage`, `tabularx` avec `L{3cm}`/`Y`, `\rowcolor{accentlight}`, `\section*{...}` + `\phantomsection` + `\addcontentsline`) sont donc utilisées **telles que spécifiées dans la mission**, sur l'hypothèse qu'elles sont définies dans un fichier de style ESPRIT détenu par l'étudiante mais absent de ce dépôt. `chapitre_conception.tex` est écrit pour être inclus (`\input`/`\include`) dans un document maître qui définit ces macros — aucune définition de macro n'est dupliquée ici.

## 13. Outillage de rendu des diagrammes

Aucun moteur PlantUML local (`plantuml.jar`) ni paquet npm/pip équivalent n'a été trouvé dans l'environnement d'exécution de cet agent (`find` sur le système de fichiers, `pip show plantuml` → présent côté bibliothèque Python mais sans serveur de rendu local ni accès réseau vérifié pour ce passage). Les fichiers `.puml` sont donc livrés en sources uniquement ; aucun `.png` n'a été généré. À régénérer par l'étudiante avec son propre outil PlantUML (extension VS Code, serveur local, ou plantuml.com).
