# 06 — Exécution des automatisations et traitement en masse (bulk/CSV)

## 1. Génération de plan — sélection, dépendances, ordre

- **Intention → plan** : `app/planner/intent_analyzer.py::analyze_business_intent` (voir `05_intelligence_artificielle.md`) puis `app/planner/plan_builder.py::build_automation_plan`.
- **Score de risque par étape** : `app/planner/plan_builder.py::_risk_level(method, quantity)` — confirmé dans le code : `DELETE` (ou équivalent destructeur) → `"high"` ; au-delà d'un certain volume ou pour certaines méthodes → `"medium"` ; sinon `"low"`. Barème numérique utilisé ensuite par la gouvernance : `low=1, medium=5, high=10` (voir `07_gouvernance_et_securite.md`).
- **Sélection ancrée dans le RAG** : `app/planner/plan_generator.py::generate_plan_selection` — contrainte vérifiée en code (pas seulement par consigne de prompt) interdisant toute clé d'endpoint absente de l'ensemble réellement retourné par la recherche sémantique — confirmé par la présence du filtrage explicite documenté dans `plan_builder.py`, cohérent avec le commentaire `PLAN_MIN_RAG_SCORE` de `app/core/config.py` sur le rôle du score RAG dans la sélection.
- **Rejet précoce** : si `analyze_business_intent` retourne une confiance insuffisante, `build_automation_plan` retourne un plan marqué `workflow_name="rejected_low_confidence"` avec `skip_reason="intent_confidence_too_long"` — confirmé littéralement dans le code (`"skip_reason": "intent_confidence_too_low"`).
- **Tri topologique** : `app/planner/step_ordering.py::topological_sort_steps` — présence confirmée ; algorithme exact non relu ligne à ligne dans ce passage (**à vérifier** si une description plus fine que « tri topologique fondé sur les dépendances de schéma » est requise).
- **Remarque de code intéressante pour le rapport** : des commentaires `ARIA-WORKFLOW-V2: Phase 4` dans `plan_builder.py` documentent une correction réelle — le champ initialement prévu `WorkflowModel.confidence_score` n'existe pas dans le modèle réel (`alembic/versions/013_workflow_entity_action_org.py`), corrigé en `.confidence`. C'est un exemple concret à citer en section Difficultés (`11_difficultes_et_limites.md`).

## 2. Exécution simple

- **Simulation obligatoire** : `app/dry_run/simulator.py` (aucun appel réseau réel) — présence confirmée, contenu interne non audité en détail.
- **Garde d'approbation** : `app/approval/approval_guard.py::assert_approval_for_real_execution(dry_run, approval_granted)` — lève `ApprovalRequiredError` si une exécution réelle (`dry_run=False`) est tentée sans `approval_granted=True`. Confirmé littéralement dans le code (fonction de 9 lignes, comportement sans ambiguïté).
- **Résolution des paramètres de chemin** (`app/automation/executor.py`) :
  - chaque valeur de paramètre est encodée via `quote(raw, safe="")` ;
  - une liste de motifs de traversée de répertoire normalisés et en minuscules est vérifiée (`%252e`, `%252f`, c'est-à-dire des variantes doublement encodées, confirmées dans le code) ;
  - la vérification est faite **avant et après** substitution (`_contains_traversal` appelé sur la valeur brute, puis sur le chemin résolu complet) ;
  - `_build_and_validate_url` vérifie explicitement que l'hôte (`netloc`) de l'URL finale n'a pas dérivé de celui de l'URL de base, levant une erreur précise sinon (*"Resolved URL host changed from ... to ..."*).
- **Client HTTP partagé** pour toute l'exécution — cité dans un document antérieur ; confirmé par cohérence architecturale mais non relu littéralement dans `executor.py` à cet endroit précis du code — **à vérifier** si une citation de ligne exacte est requise.

## 3. Exécution en masse (CSV/Excel)

- **Limites de fichier** : `app/core/config.py` → `BULK_FILE_MAX_SIZE_MB = 20`, `BULK_MAX_ROWS = 10000`.
- **Validation** : `app/bulk_validation/schema_validator.py` — présence confirmée.
- **Lots** : `BULK_BATCH_SIZE = 50` lignes par lot Celery (`app/core/config.py`, commentaire : *« Rows per Celery batch task — small enough for one task to finish in seconds »*).
- **Limite de débit globale** : `BULK_RATE_LIMIT_PER_SECOND = 10.0`, implémentée côté Redis (pas un limiteur par worker) — le commentaire du code explicite pourquoi un limiteur local ne suffirait pas (plusieurs batches d'un même job tournant simultanément sur plusieurs workers, chacun ignorant le trafic des autres). Implémentation : `app/bulk_execution/batch_executor.py` (`RedisRateLimiter`), complétée par un second limiteur simple ailleurs (`app/automation/batch_processor.py::SimpleRateLimiter`, `delay_seconds=0.1`) — **à vérifier le rôle exact et non redondant de ces deux limiteurs distincts**, ils ne semblent pas appliqués au même composant.
- **Retries** : `BULK_STEP_RETRIES = 3` (`app/core/config.py`).

## 4. Disjoncteur (circuit breaker)

`app/resilience/circuit_breaker.py::RedisCircuitBreaker`, paramètres par défaut confirmés dans le code : `failure_threshold: int = 5`, `recovery_timeout: int = 60` (secondes), `half_open_max_calls: int = 3`. Machine à états `CLOSED → OPEN (après failure_threshold échecs) → HALF_OPEN (après recovery_timeout) → CLOSED` ou retour à `OPEN`, stockée dans Redis (partagée entre workers). Instancié par endpoint cible (confirmé par la structure du module prenant une clé d'endpoint).

## 5. Idempotence

`app/idempotency/key_generator.py::generate_idempotency_key` — confirmé : hache uniquement `org_id`, `workflow_name`, `endpoint_key` et des `business_fields` fournis par l'appelant (pas la ligne complète), avec sérialisation JSON canonique (clés triées récursivement, séparateurs compacts). Le commentaire d'en-tête documente explicitement le défaut corrigé : une version antérieure hachait la ligne complète, incluant des champs volatils (timestamps, IDs de requête), ce qui empêchait toute déduplication réelle entre deux tentatives logiquement identiques. L'insertion en base avec contrainte de non-conflit est gérée par `app/idempotency/service.py` (contenu détaillé non relu dans ce passage).

## 6. Résolution de conflits 409

`app/bulk_execution/conflict_resolution.py::find_existing_record` — confirmé : compare les champs d'identité (`code`, `matricule`, etc., cités littéralement dans le commentaire du module) sur les éléments retournés, pour décider si un conflit 409 correspond sans ambiguïté à un enregistrement existant unique. `is_duplicate_conflict(status_code, response_payload)` et `_identity_fields_present` confirment la structure en deux temps (détection du statut de conflit, puis vérification d'unicité de la correspondance) décrite dans un document antérieur.

## 7. Journalisation et sanitisation au moment de l'exécution

`app/automation/service.py` et `app/bulk_execution/batch_executor.py` appellent tous deux `sanitize_payload` (défini dans `app/security/sanitizer.py`, ré-exposé par `app/audit/service.py`) avant d'écrire `request_payload`/`response_payload` dans `AutomationStepLog`. C'est le **seul** point du pipeline où une sanitisation de données sensibles est confirmée (contrairement à l'étape d'ingestion HAR — voir `03_pipeline_har.md` §8).

## 8. Écart constaté — Celery Beat et la tâche de nettoyage planifiée

`app/workers/celery_app.py` définit un `beat_schedule` réel (`cleanup-expired-files-daily`, tous les jours à 2h UTC, tâche `app/workers/tasks/cleanup.py::cleanup_expired_files`, liée à `UPLOAD_FILE_TTL_DAYS=7` / `UPLOAD_FAILED_FILE_TTL_HOURS=24`). Aucun service `celery beat` n'est démarré dans `docker-compose.yml` ni `docker-compose.prod.yml` — voir `01_architecture_et_stack.md` §4 et `10_deploiement_et_configuration.md`. **Point à clarifier avec le développeur avant de décrire cette fonctionnalité comme opérationnelle dans le rapport.**
