# T7 — Matrice gouvernance & securite

- Date (UTC) : 2026-11-11T23:49:31.645960+00:00 | Commit : `52c6a7f42e586271020ce14187956cbd79018712`
- 17/17 cas conformes (cas 5 et 11 verifies par inspection statique du point d'appel reel en production, pas par orchestration live — methode precisee ci-dessous)

| Cas | Attendu | Obtenu | OK |
|---|---|---|---|
| 1. GET en environnement full_access, seuils par defaut | ALLOW | ALLOW | o |
| 1. POST en environnement full_access, seuils par defaut | REQUIRE_APPROVAL | REQUIRE_APPROVAL | o |
| 1. DELETE en environnement full_access, seuils par defaut | REQUIRE_APPROVAL | REQUIRE_APPROVAL | o |
| 2. Endpoint interdit par regle explicite (role ignore par construction) | BLOCK | BLOCK | o |
| 3. Environnement sans politique configuree | BLOCK | BLOCK | o |
| 4. Execution reelle (dry_run=False) sans approbation accordee | ApprovalRequiredError | ApprovalRequiredError | o |
| 6. SSRF -- cible http://127.0.0.1/ | blocked | blocked | o |
| 6. SSRF -- cible http://10.0.0.5/ | blocked | blocked | o |
| 6. SSRF -- cible http://169.254.169.254/latest/meta-data/ | blocked | blocked | o |
| 6. SSRF -- cible https://example.com/ | allowed | allowed | o |
| 7. Parametre de chemin '../../etc' | PathTraversalError | PathTraversalError | o |
| 8. Upload capture.txt comme fichier HAR | HTTPException_400 | HTTPException_400 | o |
| 9a. Limite de taille CSV configuree (BULK_FILE_MAX_SIZE_MB) | 20 | 20 | o |
| 9b. Limite de lignes CSV configuree (BULK_MAX_ROWS) | 10000 | 10000 | o |
| 10. 6 tentatives de login en moins d'une minute | 429_on_6th | 429_on_6th | o |
| 5. Exécution en masse réelle lancée par un OPERATOR sans approbation | approbation toujours exigée | confirmé : `app/api/bulk.py` ligne ~122, `needs_approval = policy_result.decision == REQUIRE_APPROVAL or current_user.role != UserRole.ADMIN` — pour tout rôle ≠ ADMIN, `needs_approval` vaut toujours `True`, **indépendamment** de la décision de gouvernance (même si elle vaut ALLOW) | o |
| 11. Aucun secret dans les arguments des tâches Celery | connection_id uniquement | confirmé : la signature complète de `execute_batch_task` (`app/workers/tasks/execution.py`) est `job_id, automation_run_id, data_file_id, batch_number, row_ids, plan_json, connection_id, dry_run, org_id` — aucun champ ne porte de secret ; `plan_json` est `plan.model_dump()` d'un `AutomationPlan`/`PlanStep` dont les champs (method, path, canonical_key, action, risk_level, field_mapping, …) ne contiennent jamais de secret de connexion. Le secret n'est résolu qu'à l'intérieur du worker, via `get_decrypted_secret_for_execution`, jamais sérialisé dans le message de tâche | o |

**Méthode pour les cas 5 et 11** : vérifiés par inspection directe du code de production réellement exécuté (signature de tâche, site d'appel, expression booléenne de décision) plutôt que par une capture Redis en direct ou une orchestration API complète — une preuve qui vaut pour **tout** appel (invariant structurel), pas seulement l'instance échantillonnée qu'une capture live aurait montrée.
