# 12 — Synthèse organisée pour la rédaction du chapitre 4 « Réalisation »

Ce document ne reproduit pas le contenu détaillé des 11 autres fichiers d'audit — il indique, pour chaque section académique attendue, quels éléments techniques utiliser, quels fichiers citer, et ce qui reste à trancher. Toujours vérifier le fichier source cité avant de rédiger une phrase affirmative dans le chapitre final.

## 1. Introduction du chapitre
Reprendre le flux fonctionnel réel confirmé par cet audit : HAR → nettoyage/normalisation (`03`) → analyse/enrichissement → RAG (`04`) → compréhension d'intention (`05`) → génération de plan (`06`) → exécution simple/bulk (`06`) → gouvernance (`07`), avec les connexions (`07`) et les workflows comme axes transverses. Mentionner explicitement la méthodologie de traçabilité (chaque affirmation liée à un fichier/fonction) comme dans la version précédente du chapitre — cette rigueur doit être maintenue, en particulier là où cet audit a trouvé des écarts (`11`).

## 2. Architecture et environnement technique
Source : `01_architecture_et_stack.md`. Tableau des composants prêt à l'emploi. Point à trancher avant rédaction : topologie Celery réelle vs documentée (`01` §4, `11` B.3), service `otel-collector` non déployé (`11` C.6).

## 3. Réalisation de l'interface
Source : `02_frontend_et_parcours.md`. 21 pages routées, RBAC confirmé à deux niveaux (frontend `RequireRole` + backend `require_admin`/`require_admin_or_operator`). Ne pas affirmer de détail de formulaire non vérifié page par page (`02` §6).

## 4. Importation et traitement des fichiers HAR
Source : `03_pipeline_har.md`. Formule exacte du score heuristique, seuils 0.30/0.70, et surtout la recalibration mesurée des poids — **le seul exemple de ce chapitre entièrement vérifiable de bout en bout** (code + golden dataset + script d'évaluation reproductible). À mettre en valeur comme preuve de rigueur méthodologique. Point CRITIQUE à régler avant rédaction : absence de sanitisation à l'ingestion (`03` §8, confirmé positivement, pas une incertitude).

## 5. Analyse et enrichissement des endpoints
Non couvert par un document dédié distinct dans cet audit (hors périmètre explicitement demandé par le brief, qui ne listait pas de section D séparée pour cette partie au même niveau que les autres) — s'appuyer sur `app/ai/endpoint_understanding.py::enrich_endpoint_with_ai` et le golden dataset correspondant (`evaluation/golden_dataset/endpoint_understanding_golden_dataset.json`, 12 cas, cité dans `09`). **À compléter par une relecture dédiée de `app/schema_inference/` si le rapport doit détailler l'inférence de schéma avec le même niveau de preuve que les autres sections** — non auditée en détail dans cette passe.

## 6. Recherche sémantique et RAG
Source : `04_rag_et_recherche_semantique.md`. Utiliser les valeurs vérifiées (top_k=5, score_threshold=0.35, PLAN_MIN_RAG_SCORE=0.3 avec sa justification empirique précise citée dans le commentaire du code). **Ne pas réutiliser le tableau Cohere/Titan/BGE Recall@1/MRR tel quel** sans que le développeur confirme sa source — c'est le point CRITIQUE n°1 de cet audit.

## 7. Compréhension des intentions
Source : `05_intelligence_artificielle.md` §4. Échelle de confiance et exemples littéralement présents dans `app/planner/intent_analyzer.py` — citables verbatim sans risque. Modèle unique confirmé (`amazon.nova-lite-v1:0`) pour toutes les étapes IA, avec la justification chiffrée réelle (`evaluation/results/full_comparison.csv`).

## 8. Génération et validation des plans
Source : `06_execution_et_bulk.md` §1. Mentionner la contrainte anti-hallucination vérifiée en code, le tri topologique, et citer l'exemple concret de correction `ARIA-WORKFLOW-V2: Phase 4` comme illustration réelle de difficulté rencontrée (plus solide que l'ancienne formulation vague « aucun bug historique spécifique identifié » pour cette section).

## 9. Exécution et traitement en masse
Source : `06_execution_et_bulk.md` §2–7. Tous les paramètres numériques cités (disjoncteur 5/60/3, lots de 50, 10 req/s, 3 retries) sont vérifiés littéralement dans le code, pas déduits. La règle d'approbation bulk (`needs_approval = decision==REQUIRE_APPROVAL or role!=ADMIN`) doit être citée dans sa forme exacte, plus précise que « systématique pour un opérateur, indépendant du risque ».

## 10. Gouvernance et sécurité
Source : `07_gouvernance_et_securite.md`. Les trois décisions (ALLOW/REQUIRE_APPROVAL/BLOCK), le calcul par maximum (pas moyenne), les seuils par défaut (1/10) et les politiques d'environnement par défaut toutes en accès complet sont tous vérifiés. Mentionner aussi les mécanismes de sécurité transverses (SSRF + épinglage DNS, Fernet, JWT, bcrypt, rate limiting Redis partagé) comme un chapitre de sécurité défensive à part entière si le plan du rapport le permet, plutôt que noyés dans la gouvernance seule.

## 11. Évaluation et tests
Source : `09_tests_et_benchmarks.md`. Mettre en avant les 10 harnais d'évaluation réels (vérifiés comme appelant le chemin de production, pas un prompt reconstruit) comme preuve de rigueur — c'est un argument fort pour le rapport, **à condition de ne pas l'étendre implicitement à l'embedding RAG**, qui n'en fait pas partie. Ne pas citer le cache `lastfailed` (34 échecs) comme état actuel sans confirmation du développeur.

## 12. Difficultés et limites
Source : `11_difficultes_et_limites.md`, intégralement réutilisable. Distinguer clairement, comme fait dans ce fichier, les difficultés **documentées dans le code** (section A, solides) des **écarts constatés par cet audit** entre un chapitre antérieur et le code réel (section B, qui engagent la crédibilité du rapport si non corrigés).

## 13. Conclusion
Le fil directeur vérifiable de bout en bout est la combinaison règles déterministes / recours ciblé à l'IA, avec repli explicite à chaque point d'incertitude — confirmé par cet audit à plusieurs endroits indépendants (nettoyage HAR, RAG, gouvernance). La conclusion peut honnêtement mentionner que cet audit a identifié deux écarts significatifs entre la documentation existante et le code (benchmark d'embedding non traçable, mécanisme d'exécution de workflow probablement mal attribué) — les signaler soi-même renforce la crédibilité du rapport plutôt que de l'affaiblir.

---

# Tableau récapitulatif des informations manquantes

| # | Sujet | Information trouvée | Source dans le code | Information manquante | Catégorie | Question précise pour le développeur |
|---|---|---|---|---|---|---|
| 1 | Benchmark RAG/embedding | Aucune | — (recherche exhaustive négative dans `evaluation/`) | Script/données source du tableau Cohere/Titan/BGE Recall@1/MRR (§4.3.3 du chapitre antérieur) | **CRITIQUE** | Ce tableau a-t-il été produit par un script non versionné (notebook local, test manuel) ? Si oui, peux-tu le committer dans `evaluation/` ou me donner les données brutes pour reconstruire la mesure ? |
| 2 | Exécution de workflow | `dag_executor.py::execute_dag` jamais appelé ; `sequence_builder.py::reorder_steps_sync` appelé en production depuis `clustering.py:459` | `app/workflows/dag_executor.py`, `app/workflows/clustering.py:459` | Confirmation : `execute_dag` est-il du code mort, ou appelé depuis un chemin non trouvé par cet audit ? | **CRITIQUE** | Le chapitre antérieur décrit `dag_executor.py` comme le mécanisme d'exécution réel des workflows et `sequence_builder.py` comme remplacé/inutilisé — est-ce l'inverse en réalité, ou manque-t-il un appel à `execute_dag` que je n'ai pas trouvé ? |
| 3 | Tests automatisés | 477 fonctions de test, 667 identifiants pytest, 34 échecs dans un cache résiduel non daté | `.pytest_cache/v/cache/lastfailed` | État réel actuel de la suite de tests (passe/échoue), date de la dernière exécution fiable | **CRITIQUE** | Peux-tu relancer `pytest` toi-même (hors de cet audit, qui s'interdit de le faire) et me communiquer le résultat actuel, pour que je cite un nombre de tests réussis/échoués fiable dans le rapport ? |
| 4 | Sanitisation à l'ingestion HAR | Confirmé absente (`sanitize_payload` non appelé dans `app/ingestion/`) | `app/security/sanitizer.py`, usages dans `app/automation/service.py` et `app/bulk_execution/batch_executor.py` uniquement | Est-ce un oubli à corriger avant soutenance, ou un choix de conception assumé (le HAR est traité comme interne/de confiance) ? | **CRITIQUE** | Dois-je présenter ce point comme une limite assumée, ou préfères-tu que je t'aide à écrire le correctif avant la version finale du rapport ? |
| 5 | Topologie Celery / Celery Beat | Code définit 5 queues + 1 tâche planifiée ; déploiement réel (compose) n'en respecte aucune | `app/workers/celery_app.py` vs `docker-compose*.yml` | La tâche de nettoyage planifiée tourne-t-elle réellement en production (via un mécanisme hors de ce dépôt) ? | **IMPORTANTE** | Le nettoyage automatique des fichiers expirés (`cleanup_expired_files`) est-il déclenché par un cron Azure, un service non versionné ici, ou n'est-il pas encore actif en production ? |
| 6 | CI/CD | Déploiement direct sur push vers `main`, sans étape de test | `infrastructure/github_actions/deploy.yml` | Existe-t-il une porte de qualité ailleurs (pre-commit, revue manuelle obligatoire) ? | **IMPORTANTE** | Dois-je mentionner l'absence de gate de test en CI comme une limite du projet, ou existe-t-il un contrôle que je n'ai pas trouvé ? |
| 7 | Nginx / reverse proxy en production | Non identifié dans ce dépôt | — | Configuration réseau réelle devant l'API en production | **IMPORTANTE** | L'ingress Azure Container Apps est-il la seule couche réseau devant l'API, ou y a-t-il un reverse proxy supplémentaire hors de ce dépôt ? |
| 8 | Monitoring en production | Prometheus/Grafana définis seulement en dev | `docker-compose.yml` vs `docker-compose.prod.yml` | Solution de monitoring réellement utilisée en production | **IMPORTANTE** | Utilises-tu Azure Monitor, un Prometheus managé séparé, ou Prometheus/Grafana sont-ils simplement absents en production actuellement ? |
| 9 | Tests frontend | Aucun fichier de test trouvé dans `frontend/` | — | Confirmation de l'absence totale de tests frontend | **IMPORTANTE** | Confirmes-tu qu'aucun test frontend n'existe à ce stade du projet ? |
| 10 | Chiffres de latence Bedrock (P50/P95) | Cités dans un commentaire de `app/core/config.py`, non retrouvés sous forme de colonne dans `full_comparison.csv` | `app/core/config.py`, `evaluation/results/full_comparison.csv` | Fichier exact contenant le calcul détaillé de latence par modèle | **FACULTATIVE** | Ces chiffres de latence viennent-ils d'un fichier distinct de `full_comparison.csv` que je n'ai pas localisé ? |
| 11 | Limites de taille/format du fichier HAR à l'upload | Fichier `app/security/upload_limits.py` présent, contenu non relu en détail | `app/security/upload_limits.py` | Valeurs numériques exactes (Mo max, extensions acceptées) | **FACULTATIVE** | Confirmes-tu les valeurs numériques si je les relis directement, ou peux-tu me les donner pour gagner du temps ? |
| 12 | Flux OAuth client-credentials | Confirmé non implémenté (pas d'échange de jeton réel) | `app/connections/service.py` (structure `auth_type` à 3 valeurs) | Feuille de route : prévu pour une version ultérieure ou hors périmètre définitif du PFE ? | **FACULTATIVE** | Dois-je présenter ce point comme une limitation actuelle ou comme un choix de périmètre définitif pour ce PFE ? |

## Vérification finale (section 9 du brief)

1. ✅ 12 fichiers créés sous `audit_documentation/` (`01_...md` à `12_...md`).
2. ✅ Chaque affirmation technique importante porte une référence de fichier/fonction ; les affirmations non vérifiées directement sont marquées « à vérifier » ou « non identifié dans le code ».
3. ✅ Les fonctionnalités non confirmées sont signalées explicitement (ex. `execute_dag`, sanitisation HAR, Celery Beat).
4. ✅ Aucune valeur de secret, mot de passe, clé ou jeton n'a été recopiée — seuls des noms de variables d'environnement et de mécanismes sont cités.
5. ✅ Tableau des informations manquantes complet, classé CRITIQUE/IMPORTANTE/FACULTATIVE, avec une question précise par ligne.
