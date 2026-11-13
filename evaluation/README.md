# Harness d'évaluation ARIA

Couvre les 10 points d'appel LLM réels du projet (voir le détail de chacun
dans `app/ai/`, `app/planner/` et `app/workflows/`) : normalisation
sémantique et de groupe, intent + génération de plan (planner/RAG),
classification de trafic, regroupement de workflows, enrichissement
d'endpoint, réordonnancement d'étapes, description de workflow, et
canonicalisation de domaines. Chaque jeu de données est construit à partir
du prompt/schéma/payload réellement utilisés en production (vérifiés par
lecture directe du code, pas déduits de la documentation), et chaque harness
appelle le même chemin de code que la production — jamais un prompt isolé
reconstruit à côté.

## Structure

```
golden_dataset/
  planner_golden_dataset.json        — 50 cas (10A + 10B + 10C + 8D + 7E + 5F), pipeline planner/RAG
                                        A=bulk CSV/Excel, B=action unitaire, C=instruction incompréhensible,
                                        D=confiance ambiguë (0.25-0.7), E=multi-étapes avec dépendance,
                                        F=cas pièges CSV
  normalization_golden_dataset.json  — 55 cas, les 2 points de normalisation
  traffic_classification_golden_dataset.json — 30 cas, filtre du bruit (app/ingestion/semantic_filter.py)
                                        4 strates : zone grise claire, bruit déguisé en métier,
                                        métier déguisé en bruit, vraiment ambigu
  workflow_grouping_golden_dataset.json — 10 scénarios (53 endpoints), regroupement en processus
                                        métier (app/workflows/clustering.py::_semantic_cluster_llm)
                                        pièges anti-sur-découpage et anti-sur-fusion inclus
  endpoint_understanding_golden_dataset.json — 12 cas, enrichissement d'endpoint
                                        (app/ai/endpoint_understanding.py::enrich_endpoint_with_ai)
                                        4 strates : confirm_existing, refine_wrong_existing,
                                        infer_from_null, sparse_schema_low_confidence (teste la
                                        règle du prompt : confidence < 0.5 sur schéma pauvre)
  sequence_reorder_golden_dataset.json — 13 cas, réordonnancement d'étapes
                                        (app/workflows/sequence_builder.py::reorder_steps_sync)
                                        6 rule_type : auth_first, delete_last, post_before_get,
                                        parent_child, already_correct (piège anti-sur-correction),
                                        genuinely_ambiguous (piège confiance, seuil réel 0.60)
  workflow_description_golden_dataset.json — 12 cas, description + estimation de risque de
                                        workflow (app/workflows/workflow_descriptor.py::
                                        generate_workflow_description) ; catégories calées sur
                                        les 3 règles explicites du prompt pour 'high' (delete,
                                        paiement, bulk irréversible), 'medium' (mutation critique
                                        sans delete), 'low' (lecture seule / faible enjeu), plus
                                        2 cas ambigus (piège confiance <0.8)
  domain_canonicalization_golden_dataset.json — 10 cas, fusion des labels de domaine métier
                                        quasi-doublons (app/ai/domain_canonicalization.py, appelé
                                        par app/planner/service.py::_canonicalize_domains) ;
                                        inclut le contre-exemple donné par le prompt lui-même
                                        (localization/monitoring — ne pas fusionner) et un test
                                        de charge à 4 domaines simultanés (dc_007)
tracer/
  planner_tracer.py                  — instrumentation pipeline planner (EVAL_MODE only)
  __init__.py                        — shim de compat pour app/planner/{service,plan_builder}.py
judge/
  planner_judge.py                   — LLM-as-judge via Bedrock (modèle indépendant du pipeline testé)
  __init__.py                        — shim de compat pour tests/unit/test_judge.py
metrics/
  planner_metrics.py                 — hit rate / MRR / precision / conformity / mapping
  normalization_metrics.py           — hit rate / precision / naming accuracy / consistency
  traffic_classification_metrics.py  — accuracy / precision / recall / F1 / domain+action match / bornes de confiance
  workflow_grouping_metrics.py       — precision/recall/F1 par paires de co-appartenance, complétude des
                                        indices, nombre de groupes, qualité du nommage
  endpoint_understanding_metrics.py  — correspondance domaine/action, pertinence des tags, calibration
                                        de la confiance (résumé/description non notés — texte libre)
  sequence_reorder_metrics.py        — intégrité des clés (pas de perte/doublon/invention), respect des
                                        contraintes d'ordre relatif par cas, calibration de la confiance
                                        contre le seuil réel _REORDER_MIN_CONFIDENCE=0.60
  workflow_description_metrics.py    — correspondance du niveau de risque contre les règles explicites
                                        du prompt, pertinence des tags, calibration de risk_confidence
                                        (résumé/description non notés — texte libre)
  domain_canonicalization_metrics.py — exactitude du nombre de domaines canoniques (ni sous- ni
                                        sur-fusion), couverture de chaque domaine attendu, préservation
                                        de la distinction entre domaines réellement différents — scoré
                                        au niveau de l'ensemble final, pas d'un mapping brut→canonique
                                        (la production elle-même n'expose jamais ce mapping)
run_scripts/
  run_full_comparison.py             — AGRÉGATEUR : lit tous les summary_<tâche>.json présents dans
                                        results/ (écrits par chaque run_*_eval.py --models ... à la fin
                                        de son run_comparison()) et calcule UN classement pondéré par
                                        modèle, tous coûts et sans appel LLM. Voir aggregate.py pour les
                                        poids/justifications par tâche.
  run_planner_eval.py                — harness planner/RAG + export CSV
  run_normalization_eval.py          — harness normalisation (déterministe par défaut, --with-ai pour le fallback LLM réel)
  run_normalization_stress_test.py   — stress test structurel (~450 URLs synthétiques)
  run_traffic_classification_eval.py — harness classification de trafic, appelle le VRAI
                                        client.classify_api_call() (prompt/schéma/validation de production)
  run_workflow_grouping_eval.py      — harness regroupement de workflows, reproduit exactement le payload
                                        et le prompt de _semantic_cluster_llm ; scoré par précision/rappel
                                        par paires de co-appartenance (pas de label unique en clustering)
  run_endpoint_understanding_eval.py — harness enrichissement d'endpoint, appelle le VRAI SYSTEM_PROMPT
                                        et ENDPOINT_UNDERSTANDING_SCHEMA de enrich_endpoint_with_ai()
  run_sequence_reorder_eval.py       — harness réordonnancement d'étapes, appelle le VRAI _REORDER_SYSTEM
                                        et _REORDER_SCHEMA de reorder_steps_sync(), même forme de payload
                                        (steps: [{key, method, path, summary}])
  run_workflow_description_eval.py   — harness description de workflow, appelle le VRAI _SYSTEM/_SCHEMA
                                        de generate_workflow_description(), même forme de payload
                                        (workflow_steps: texte numéroté, step_count)
  run_domain_canonicalization_eval.py — harness canonicalisation de domaines, appelle le VRAI
                                        SYSTEM_PROMPT/DOMAIN_CANONICALIZATION_SCHEMA et
                                        build_canonicalization_payload() de app/ai/domain_canonicalization.py
results/
  *.csv                              — généré après chaque run (gitignore)
```

## Lancer l'évaluation planner/RAG

Doit tourner là où `settings.DATABASE_URL` est résolvable — dans ce projet
l'hôte `postgres` n'existe que sur le réseau Docker, donc depuis la machine
hôte Windows la commande échoue (`could not translate host name "postgres"`).
Lancer depuis le conteneur `aria-api` :

```bash
docker compose exec -e EVAL_MODE=true api python evaluation/run_scripts/run_planner_eval.py
```

(équivalent local, si un jour l'API tourne hors Docker avec Postgres
accessible directement) :

```bash
EVAL_MODE=true python evaluation/run_scripts/run_planner_eval.py
```

## Lancer l'évaluation normalisation (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_normalization_eval              # déterministe, gratuit
python -m evaluation.run_scripts.run_normalization_eval --with-ai    # coûte des tokens Bedrock réels
python -m evaluation.run_scripts.run_normalization_stress_test       # stress test structurel
```

## Lancer l'évaluation classification de trafic (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_traffic_classification_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Appelle directement `client.classify_api_call()` (via `TracingClient` pour le
suivi de coût/budget) — même prompt, même schéma, même validation Pydantic
que `app/ingestion/semantic_filter.py` en production. Contrairement au
harnais de détection de paramètres, ce n'est pas un prompt isolé : c'est le
vrai chemin de code exécuté.

## Lancer l'évaluation regroupement de workflows (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_workflow_grouping_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Reproduit exactement le payload et le prompt de
`app/workflows/clustering.py::_semantic_cluster_llm`. Le regroupement n'a pas
de label unique par item (deux partitions différentes peuvent être également
correctes) donc le score utilisé est la précision/rappel/F1 **par paires de
co-appartenance** contre la partition annotée, pas une comparaison groupe à
groupe.

## Lancer l'évaluation enrichissement d'endpoint (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_endpoint_understanding_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Appelle le même `SYSTEM_PROMPT`/`ENDPOINT_UNDERSTANDING_SCHEMA` que
`enrich_endpoint_with_ai()`. `summary`/`description` sont du texte libre sans
vérité unique et ne sont volontairement pas notés (pas de juge LLM branché
pour cette tâche) ; seuls domaine/action/tags/calibration de confiance le
sont.

## Lancer l'évaluation réordonnancement d'étapes (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_sequence_reorder_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Appelle le même `_REORDER_SYSTEM`/`_REORDER_SCHEMA` que
`reorder_steps_sync()`. Comme un réordonnancement n'a pas toujours une seule
permutation correcte (deux ressources indépendantes peuvent être dans
n'importe quel ordre l'une par rapport à l'autre), chaque cas encode des
**contraintes d'ordre relatif** (paire de clés A doit précéder B) plutôt
qu'une séquence exacte imposée — reflet direct des 4 règles énoncées par le
prompt système lui-même (auth d'abord, POST avant GET, DELETE en dernier,
parent avant enfant). Inclut aussi des pièges anti-sur-correction (séquence
déjà correcte) et un piège de confiance (aucune règle applicable → la
confiance ne doit pas dépasser le seuil réel de déclenchement 0.60).

## Lancer l'évaluation description de workflow (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_workflow_description_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Appelle le même `_SYSTEM`/`_SCHEMA` que `generate_workflow_description()`.
`summary`/`description` sont du texte libre non noté (pas de juge LLM
branché) ; seuls `estimated_risk` (contre les 3 règles explicites du prompt :
DELETE/paiement/bulk irréversible → high, mutation critique sans delete →
medium, lecture seule/faible enjeu → low), la pertinence des tags et la
calibration de `risk_confidence` le sont. Inclut 2 cas volontairement
ambigus où plusieurs niveaux de risque sont acceptés tant que la confiance
reste <0.8, conformément à la règle du prompt.

## Lancer l'évaluation canonicalisation de domaines (aucune base de données requise)

```bash
python -m evaluation.run_scripts.run_domain_canonicalization_eval \
    --models deepseek.v3.2,amazon.nova-lite-v1:0,mistral.mistral-large-2402-v1:0 \
    --budget 0.30
```

Appelle le même `SYSTEM_PROMPT`/`DOMAIN_CANONICALIZATION_SCHEMA` que
`_canonicalize_domains()`. Contrairement aux autres tâches, la sortie
(`canonical_domains`) ne contient aucun mapping vers les labels bruts
d'origine — la production elle-même ne consomme que la liste finale — donc
le score porte sur l'ensemble final : le bon nombre de domaines distincts
(ni sous- ni sur-fusion) et la couverture de chacun. Inclut le
contre-exemple donné littéralement par le prompt système lui-même
(`localization`/`monitoring` — piège anti-sur-fusion) et un test de charge à
4 domaines simultanés.

## Obtenir UN classement final entre modèles (agrégation pondérée)

Chaque harness ci-dessus produit son propre tableau isolé. Pour transformer
ça en une seule décision par modèle, après avoir lancé un ou plusieurs des 6
harnais `--models ...` (peu importe l'ordre, peu importe combien) :

```bash
python -m evaluation.run_scripts.run_full_comparison
```

Ne fait AUCUN appel LLM — il lit uniquement `evaluation/results/summary_<tâche>.json`,
déjà écrits par les runs précédents. Il calcule, par modèle : un score de
qualité pondéré (0-100%, renormalisé sur les seules tâches effectivement
lancées — une tâche non lancée n'est pas comptée comme un échec), le coût
total réellement dépensé sur ces tâches, et un ratio qualité/$ pour départager
deux modèles proches en qualité mais pas en coût. Les poids par tâche (et
pourquoi) sont documentés en tête de `evaluation/aggregate.py` — c'est un
jugement explicite basé sur la fréquence d'appel réelle et l'impact d'une
erreur (le planner pèse 20/100 car il produit directement des plans exécutés
contre de vraies APIs ; la canonicalisation de domaines pèse 10/100 malgré
une fréquence d'appel faible car son propre docstring documente un vrai bug
silencieux qu'elle corrige). Les poids sont éditables directement dans ce
fichier si ce jugement ne correspond pas au tien.

`run_planner_eval.py` et `run_normalization_eval.py` ne s'intègrent pas
encore automatiquement (harnais DB-bound / mono-modèle, forme différente des
6 autres) — leurs poids sont réservés dans `aggregate.py` mais leur score
reste absent du classement tant qu'aucun `summary_planner_plan_generation.json`
/ `summary_normalization.json` n'est déposé manuellement dans `results/` au
même format que les 6 autres.

## Interpréter les résultats (planner/RAG)

- Hit rate > 0.7  → le RAG retrouve les bons endpoints
- MRR > 0.6       → le bon endpoint arrive en tête
- Mapping > 0.8   → le CSV→API mapping fonctionne (catégorie A)
- Faithfulness > 4/5 → pas d'hallucination d'endpoints
- Completeness > 3/5 → les étapes implicites sont détectées

## Notes d'implémentation (écarts par rapport à un pipeline "propre")

- `golden_dataset.json` fixe `run_id`/`org_id` par cas — les cas ciblent 2
  runs HAR réellement ingérés (`test_hr_api.har`, `shopflow_trace.har`),
  pas un run générique inexistant.
- Les catégories A/B utilisent `run_id`/`org_id` explicites plutôt qu'un
  run global unique : aucun run ingéré ne couvre à la fois RH et
  e-commerce/auth.
- `metrics.py` normalise `canonical_key` (`{org_id}:{METHOD} /path` →
  `{METHOD} /path`) avant toute comparaison au golden dataset — sans ça,
  aucune métrique basée sur les steps ne matcherait jamais.
- `judge.py` appelle `ai_client.structured_chat(model=JUDGE_MODEL)` avec le
  modèle explicitement forcé en paramètre — indépendant de
  `settings.BEDROCK_MODEL` (le pipeline testé), pour ne jamais noter un
  modèle avec lui-même.
