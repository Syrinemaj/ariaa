# 09 — Tests et benchmarks

> Règle appliquée dans cet audit : aucune suite de tests n'a été exécutée (risque d'appel à Bedrock facturé ou de modification de données). Les chiffres ci-dessous viennent soit d'un comptage statique du code, soit d'artefacts déjà présents dans le dépôt (`.pytest_cache/`, `evaluation/results/`).

## 1. Inventaire des tests

- **47 fichiers** sous `tests/unit/`, **9 fichiers** sous `tests/integration/` (dont un sous-dossier `tests/integration/real_db/`, laissant supposer une distinction entre intégration avec base mockée et avec base réelle — **à vérifier**).
- **477 fonctions `def test_...`** comptées directement par `grep` sur `tests/`.
- Le cache local `.pytest_cache/v/cache/nodeids` (résidu d'une exécution antérieure, non relancée par cet audit) liste **667 identifiants de test** au total — un nombre plus élevé que le comptage de fonctions `def test_` car il inclut les cas paramétrés (plusieurs identifiants pour une même fonction `@pytest.mark.parametrize`).
- Le même cache (`lastfailed`) liste **34 tests marqués en échec** lors de cette exécution antérieure non datée, parmi lesquels `tests/integration/test_auth_integration.py::test_login_admin_success`, plusieurs tests de `test_rbac_integration.py`, `test_governance_api.py`, `test_embedding_cache.py`, `test_redis_circuit_breaker.py`, `test_path_traversal.py`, `test_workflow_clustering.py`. **Avertissement explicite** : ce fichier est un résidu local d'une session de développement antérieure, non horodaté de façon fiable, et n'a pas été reproduit par cet audit (conformément à la règle de ne pas relancer de suite de tests). Il ne doit **pas** être cité dans le rapport comme "l'état actuel des tests" sans que le développeur confirme quand et pourquoi ces échecs sont survenus (régression réelle, environnement local incomplet type base de données non démarrée, etc.). C'est un point à faire valider explicitement — voir le tableau des manques.
- Présence confirmée d'un fichier `tests/unit/test_groq_client.py` — nom résiduel de l'époque multi-fournisseur (Groq a été retiré du code de production, voir `05_intelligence_artificielle.md` §1) ; **à vérifier** si ce fichier teste encore un module réellement présent ou s'il est devenu obsolète lui-même.

## 2. Couverture par domaine (déduite des noms de fichiers de `tests/`, non du contenu détaillé de chacun)

Présence confirmée de fichiers de test couvrant (liste partielle, non exhaustive) : authentification/RBAC, gouvernance, disjoncteur Redis, traversée de chemin, cache d'embedding, clustering de workflows, service de connexions, pagination des rapports. **Aucun répertoire de test frontend n'a été localisé** dans `frontend/` (voir `02_frontend_et_parcours.md`).

## 3. Harnais d'évaluation IA (`evaluation/`) — distinct des tests unitaires

`evaluation/README.md` documente **10 jeux de données dorés**, un par point d'appel LLM réel du pipeline, chacun appelant explicitement le même chemin de code que la production (prompt, schéma, fonction réels — pas une reconstruction isolée) :

| Jeu de données | Cas | Point du pipeline testé |
| --- | --- | --- |
| `planner_golden_dataset.json` | 50 | `app/planner/` (intent + plan) |
| `normalization_golden_dataset.json` | 55 | normalisation (2 points) |
| `traffic_classification_golden_dataset.json` | 30 | `app/ingestion/semantic_filter.py` |
| `workflow_grouping_golden_dataset.json` | 10 scénarios / 53 endpoints | `app/workflows/clustering.py::_semantic_cluster_llm` |
| `endpoint_understanding_golden_dataset.json` | 12 | `app/ai/endpoint_understanding.py::enrich_endpoint_with_ai` |
| `sequence_reorder_golden_dataset.json` | 13 | `app/workflows/sequence_builder.py::reorder_steps_sync` |
| `workflow_description_golden_dataset.json` | 12 | `app/workflows/workflow_descriptor.py::generate_workflow_description` |
| `domain_canonicalization_golden_dataset.json` | 10 | `app/ai/domain_canonicalization.py` |

Chaque jeu dispose d'un script `run_*_eval.py` et d'un module de métriques dédié (`evaluation/metrics/`). Un agrégateur (`evaluation/run_scripts/run_full_comparison.py` + `evaluation/aggregate.py`) combine les résultats par modèle en un score pondéré unique, sans appel LLM supplémentaire — c'est la source directe du tableau de comparaison `amazon.nova-lite-v1:0` vs `deepseek.v3.2` vs `mistral.mistral-large-2402-v1:0` cité dans `05_intelligence_artificielle.md`, vérifié ligne par ligne dans `evaluation/results/full_comparison.csv`.

**Note opérationnelle confirmée dans le README** : l'évaluation planner/RAG doit s'exécuter dans le conteneur `aria-api` (le nom d'hôte `postgres` n'est résolvable que sur le réseau Docker) ; l'évaluation de normalisation peut tourner sans base de données, en mode déterministe gratuit par défaut (`--with-ai` déclenche des appels Bedrock réels facturés).

## 4. Point CRITIQUE — benchmark RAG/embedding non traçable

Voir `04_rag_et_recherche_semantique.md` §7 : le tableau comparant Cohere/Titan/BGE par Recall@1 et MRR, cité dans `rapport/chapitre_realisation.md` §4.3.3, **ne correspond à aucun des 10 harnais listés ci-dessus** et à aucun autre script trouvé dans `evaluation/`. Ce point doit être résolu avant la rédaction finale du chapitre 4 (CRITIQUE).

## 5. Benchmarks de latence et de coût réellement présents

`evaluation/run_scripts/run_latency_benchmark.py` existe (présence confirmée ; contenu détaillé non audité dans ce passage). Les chiffres de latence P50/P95 cités dans `app/core/config.py` (commentaire sur `BEDROCK_MODEL`) sont traçables à `evaluation/aggregate.py` + `evaluation/results/full_comparison.csv`, qui contient effectivement les colonnes de coût/score par modèle (vérifié directement), mais **ne contient pas de colonne de latence P50/P95 dans l'extrait relu** — **à vérifier** où exactement ces deux chiffres (1.7s/2.1s, 4.1s/63s) sont stockés/calculés si une citation plus précise que "commentaire du fichier de configuration" est nécessaire pour le rapport.

## 6. Ce qui reste à faire pour cette section avant rédaction finale

- Confirmer avec le développeur si les 34 échecs de `.pytest_cache/v/cache/lastfailed` reflètent un état réel actuel ou un résidu obsolète (CRITIQUE).
- Obtenir ou reconstruire la source du benchmark RAG/embedding (CRITIQUE).
- Confirmer l'existence ou l'absence de tests frontend (IMPORTANTE).
- Localiser précisément la source des chiffres de latence P50/P95 Bedrock (IMPORTANTE).
