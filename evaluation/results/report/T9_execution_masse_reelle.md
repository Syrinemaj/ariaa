# T9 — Exécution en masse **réelle** contre `absence-app`

- **Date :** 12/11/2026.
- **Script :** `evaluation/report_tests/t9_bulk_reel.py`. Les données brutes sont dans `T9_state.json`.
- **Cible :** `absence-app` (FastAPI + SQLite), démarrée sur `0.0.0.0:8010`. Sa base a été sauvegardée avant les essais (`absences.db.before-bulk-reel-20261112-230912`).
- **Accès depuis ARIA :** connexion `http://host.docker.internal:8010`, de type `service_account` (jeton de session administrateur d'absence-app).
- **Pourquoi T8 avait échoué :** T8 visait `localhost`, que la protection SSRF bloque toujours, par conception. Un **nom d'hôte** de développement (`host.docker.internal`) est la voie prévue par la protection en mode développement (`ALLOW_HTTP_TARGETS=true`, déjà actif). **La protection SSRF n'a pas été modifiée.**
- **Plans :** une étape chacun, `POST /api/requests` et `POST /api/employees`, avec le schéma de requête que fournirait le catalogue.
- **Parcours testé :** le parcours réel complet, c'est-à-dire import, association des colonnes, validation, exécution, demande d'approbation (HTTP 403 `APPROVAL_PENDING`), approbation par l'administrateur, puis exécution.
- **Vérification :** chaque résultat est contrôlé **côté cible**, en comptant les lignes de la base SQLite.

## Résultats

| Expérience | Protocole | Résultat ARIA | Effet réel sur la cible |
|---|---|---|---|
| Exécution nominale | 100 demandes d'absence (`t8_bulk_100.csv`) | 100 réussies / 0 échec (≈ 35 s, approbation comprise) | `absence_requests` : 115 → **215** |
| Idempotence | **Le même fichier** importé une 2e fois puis exécuté | 100 traitées / 0 échec (≈ 19 s) | 215 → **215** (aucun doublon). Le journal de la cible ne montre **aucun** POST pendant cette exécution. |
| Doublons (409) | 11 créations d'employés : 5 nouveaux, 3 doublons visibles sur la 1re page de la liste de la cible, 3 au-delà | 11 réussies / 0 échec (≈ 24 s). Journaux d'étapes : **5 × 201, 6 × 409**, tous résolus | `employees` : 108 → **113** (5 créés, 0 doublon créé) |
| Disjoncteur | Cible **arrêtée**, 100 nouvelles demandes | 5 échecs « All connection attempts failed », puis **95 lignes `CIRCUIT_OPEN`**, court-circuitées sans appel (≈ 13 s). État dans Redis : `open`, `failures=5` | aucun changement (cible arrêtée) |
| Reprise | Cible redémarrée, attente de plus de 60 s (état semi-ouvert), nouvelle exécution du **même** fichier | 100 réussies / 0 échec (≈ 15 s). Disjoncteur **refermé** (clé Redis supprimée) | 215 → **315** |

## Défauts réels découverts pendant ces essais, puis corrigés

1. **Des erreurs de données ouvraient le disjoncteur.**
   - *Constat :* lors d'un premier essai (plan sans schéma, donc corps vide), 5 réponses **422** ont ouvert le disjoncteur pour tout le fichier.
   - *Correction :* seules les erreurs de disponibilité comptent désormais : absence de réponse, 5xx, 408, 429 (`is_health_failure` dans `batch_executor.py`).
   - *Vérifié en réel :* lors du premier essai de doublons, 5 réponses 422 n'ont **pas** ouvert le disjoncteur.
2. **Doublons non résolus au-delà de la première page.**
   - *Constat :* la recherche de l'enregistrement existant ne lisait que la 1re page de la liste (20 employés sur 108). Au premier essai, 3 doublons ont été résolus (1re page) et 3 non (pages suivantes).
   - *Correction :* la recherche parcourt maintenant la pagination numérotée (`conflict_resolution.py`, 50 pages au maximum).
   - *Vérifié en réel :* au second essai, les 6 doublons sont résolus.
3. **Impossible de relancer les lignes échouées.**
   - *Constat :* une ligne en échec prend le statut `failed`, qui n'était pas éligible à une nouvelle exécution. La relance répondait, à tort, que « toutes les lignes ont déjà été exécutées avec succès », alors que le module d'idempotence prévoit explicitement de réessayer une ligne échouée.
   - *Correction :* `ELIGIBLE_ROW_STATUSES` inclut désormais `failed` (`service.py`).
   - *Vérifié en réel :* la relance a créé les 100 demandes.

Chaque correction est couverte par de nouveaux tests unitaires (`test_breaker_health_failure.py`, `test_conflict_resolution_pagination.py`, `test_bulk_row_eligibility.py`).

## Constat, sans correction

- **La route `/bulk/resume`** ne relance que les **lots interrompus**, par exemple après la panne d'un worker. Elle ne relance pas les lignes d'un lot terminé en échec. Après une panne de la cible, la relance passe donc par une **nouvelle exécution du même fichier** (voir l'expérience « Reprise »).

## Erreurs de préparation (de ma part, pas d'ARIA)

- Premier plan nominal sans `request_schema` : corps vide, puis 422 côté cible. Le plan a été corrigé avec le schéma qu'aurait fourni le catalogue.
- Adresses `@absence-app.test` refusées par la validation e-mail de la cible (domaine réservé), donc 422. Le second fichier de doublons utilise `@example.com`.

## État des suites de tests après ces corrections

- **Tests unitaires :** 519 (488 réussis, 31 ignorés, 0 échec). Couverture globale de **42,1 %** (3 665 / 8 703 lignes). Le module d'exécution en masse est couvert à 45,7 % (150 / 328).
- **Tests d'intégration :** **109 réussis**, 0 échec, sur une base PostgreSQL neuve.
