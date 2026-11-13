# 08 — Base de données, modèles de données et API REST

## 1. SGBD et accès

PostgreSQL (image `pgvector/pgvector:pg16`) + extension **pgvector**. Accès ORM via SQLAlchemy 2.0.31, driver async `asyncpg` côté API. Migrations : Alembic, **26 fichiers** dans `alembic/versions/` (ex. `013_workflow_entity_action_org.py`, `024_embedding_dims_1024.py` — confirmés par citation directe dans le code applicatif qui s'y réfère).

## 2. Tables principales (27 recensées dans `app/models/`)

| Table (`__tablename__`) | Modèle | Rôle | Clés étrangères notables |
| --- | --- | --- | --- |
| `organizations` | `Organization` | Tenant racine (multi-organisation) | — |
| `users` | `User` | Comptes, rôle (`ADMIN`/`OPERATOR`) | — |
| `refresh_tokens` | `RefreshToken` | Jetons de rafraîchissement JWT | `users.id` (CASCADE) |
| `teams` | `Team` | Regroupement d'opérateurs | org-scoped |
| `team_members` | `TeamMember` | Association user ↔ team | `teams.id`, `users.id` |
| `analysis_runs` | `AnalysisRun` | Un run d'ingestion/analyse HAR | org/user/team-scoped |
| `endpoints` | `Endpoint` | Endpoint détecté et normalisé | `analysis_runs.id` |
| `endpoint_schemas` | `EndpointSchema` | Schéma JSON inféré (requête/réponse) | `endpoints.id` |
| `endpoint_embeddings` | `EndpointEmbedding` | Vecteur pgvector + hash de contenu | `endpoints.id` (index), colonne `vector(1024)` avec index HNSW |
| `workflows` | `WorkflowModel` | Regroupement d'endpoints en processus métier | `analysis_runs.id`, `organizations.id` |
| `workflow_steps` | `WorkflowStepModel` | Étape ordonnée d'un workflow | `workflows.id` |
| `data_files` | `DataFile` | Fichier CSV/Excel importé pour le bulk | `analysis_runs.id`, org/user-scoped |
| `data_rows` | `DataRow` | Ligne individuelle d'un `DataFile` | `data_files.id` |
| `bulk_validation_runs` | `BulkValidationRun` | Résultat de validation d'un fichier bulk | `data_files.id` |
| `bulk_validation_errors` | `BulkValidationError` | Erreur de validation par ligne | `bulk_validation_runs.id` |
| `field_mappings` | `FieldMapping` | Correspondance colonne CSV ↔ paramètre API | — |
| `automation_runs` | `AutomationRun` | Exécution (simple ou bulk) d'un plan | `analysis_runs.id`, `connections.id` (nullable), org/user/team-scoped |
| `automation_step_logs` | `AutomationStepLog` | Log par étape, payloads sanitisés | `automation_runs.id` |
| `automation_approvals` | `AutomationApproval` | Demande/décision d'approbation admin | lié à `automation_runs` |
| `bulk_batches` | `BulkBatch` | Lot de 50 lignes en traitement | — |
| `bulk_batch_rows` | `BulkBatchRow` | Ligne individuelle au sein d'un lot | `bulk_batches.id` |
| `bulk_execution_reports` | `BulkExecutionReport` | Rapport agrégé d'une exécution bulk | — |
| `idempotency_records` | `IdempotencyRecord` | Clé d'idempotence déjà traitée | — |
| `connections` | `Connection` | Connexion vers un système cible (secret chiffré) | `users.id` (created_by), org-scoped |
| `connection_operators` | `ConnectionOperator` | Assignation opérateur ↔ connexion | `connections.id`, `users.id` |
| `governance_policies` | `GovernancePolicy` | Seuils de risque + politiques d'environnement (singleton/org) | `users.id` (updated_by), org-scoped |
| `forbidden_endpoint_rules` | `ForbiddenEndpointRule` | Règles d'endpoints interdits par org | `users.id` (created_by), org-scoped |
| `notifications` | `Notification` | Notifications utilisateur | `users.id`, org/user-scoped |
| `audit_logs` | `AuditLog` | Journal d'audit des actions sensibles | `users.id` |
| `llm_calls` | `LLMCall` | Observabilité des appels Bedrock (coût, latence) | — |

Entités supplémentaires confirmées sans table dédiée nécessairement distincte à ce niveau : `app/models/embedding.py` contient aussi la définition de l'index HNSW explicite (`Index(...)`, ligne 30), confirmant que l'index vectoriel est déclaré au niveau du modèle ORM et non ajouté manuellement en migration seule.

## 3. Routes REST (regroupées par préfixe de routeur, tous confirmés dans `app/api/*.py`)

| Préfixe | Domaine fonctionnel | Nombre de routes (vérifié) | Fichier |
| --- | --- | --- | --- |
| `/auth` | Authentification (login, refresh, logout, me, mot de passe oublié/réinitialisation, demande d'accès) | 7 | `app/api/auth.py` |
| `/users` | Gestion des utilisateurs (liste, création, rôle, activation/désactivation, suppression) | 6 | `app/api/users.py` |
| `/teams` | Équipes et membres | 7 | `app/api/teams.py` |
| `/upload` | Import de fichiers HAR (brut, normalisé, lancement d'analyse async) | 3 | `app/api/upload.py` |
| `/registry` | Runs d'analyse, endpoints, workflows d'un run | 9 | `app/api/registry.py` |
| `/openapi` | Génération de la spécification OpenAPI d'un run | 1 | `app/api/openapi.py` |
| `/rag` | Indexation, recherche sémantique, enrichissement | 3 | `app/api/rag.py` |
| `/automation` | Validation de token d'intention, plan depuis workflow, génération de plan, exécution simple | 4 | `app/api/automation.py` |
| `/reports` | Rapports agrégés (automation, run, résumé, KPI, logs) | 11 | `app/api/reports.py` |
| `/bulk` | Import de données, mapping, validation, dry-run, exécution bulk, demande d'approbation, rapports | 10 | `app/api/bulk.py` |
| `/approvals` | Liste, approbation, rejet d'automatisations en attente | 3 | `app/api/approvals.py` |
| `/audit-logs` | Consultation du journal d'audit | 1 | `app/api/audit.py` |
| `/governance` | Politique de gouvernance, règles d'endpoints interdits | 5 | `app/api/governance.py` |
| `/connections` | CRUD connexions, rotation/révocation de secret, test, opérateurs assignés | 11 | `app/api/connections.py` |
| `/maintenance` | Nettoyage manuel des fichiers uploadés | 1 | `app/api/maintenance.py` |
| `/notifications` | Notifications utilisateur | 5 | `app/api/notifications.py` |
| `/jobs` | Suivi de job asynchrone (statut, progression, annulation) | 3 | `app/api/jobs.py` |
| `/llm` | Observabilité IA (résumé, comparaison de modèles, benchmarks, coûts) | 8 | `app/api/llm.py` |

**Total : 98 routes** recensées par ce comptage direct (`grep '@router\.'` sur chaque fichier de `app/api/`). Le détail méthode/authentification par route n'a pas été ressaisi route par route dans ce document pour éviter la redondance avec le code lui-même (cf. règle « éviter les répétitions ») — chaque route est protégée par au moins `Depends(get_current_user)` sauf les routes publiques explicitement listées de `/auth` (login, refresh, forgot-password, reset-password, request-access) ; les routes `ADMIN`-only (ex. `/users`, `/connections` en écriture, `/governance`) utilisent `require_admin` ou `require_roles([UserRole.ADMIN])` — cohérent avec le RBAC frontend documenté en `02_frontend_et_parcours.md`. **À VÉRIFIER route par route** si le rapport final exige un tableau exhaustif méthode/auth par route plutôt que ce regroupement.

## 4. Schémas de requête/réponse importants

Modules `app/schemas/` et schémas Pydantic locaux à chaque routeur (ex. `TokenResponse`, `CurrentUserResponse`, `AnalyzeJobResponse`, `SemanticSearchRequest`/`SemanticSearchResponse` déjà documentés en `04_rag_et_recherche_semantique.md`, `JobStatus`, `BulkJobProgress`). Inventaire exhaustif non produit dans ce document — **à compléter si nécessaire**, le dossier `app/schemas/` n'a pas été énuméré fichier par fichier dans ce passage.
