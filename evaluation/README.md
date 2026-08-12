# Harness d'évaluation ARIA

> ⚠️ README en cours de consolidation (restructuration Phase 2, en cours de
> validation avec l'utilisateur — normalisation + planner/RAG). Ce fichier
> documente pour l'instant surtout le harness **planner/RAG**. Le harness
> **normalisation** (2 points LLM confidence-gated : `semantic_normalizer.py`
> et `group_normalizer.py`) sera documenté ici à la fin du Phase 2/3 — voir
> `golden_dataset/normalization_golden_dataset.json` et
> `run_scripts/run_normalization_eval.py` / `run_normalization_stress_test.py`
> en attendant.

## Structure (post-restructuration)

```
golden_dataset/
  planner_golden_dataset.json        — 15 cas (5A + 5B + 5C), pipeline planner/RAG
  normalization_golden_dataset.json  — 55 cas, les 2 points de normalisation
tracer/
  planner_tracer.py                  — instrumentation pipeline planner (EVAL_MODE only)
  __init__.py                        — shim de compat pour app/planner/{service,plan_builder}.py
judge/
  planner_judge.py                   — LLM-as-judge via Groq (modèle indépendant du pipeline testé)
  __init__.py                        — shim de compat pour tests/unit/test_judge.py
metrics/
  planner_metrics.py                 — hit rate / MRR / precision / conformity / mapping
  normalization_metrics.py           — hit rate / precision / naming accuracy / consistency
run_scripts/
  run_planner_eval.py                — harness planner/RAG + export CSV
  run_normalization_eval.py          — harness normalisation (déterministe par défaut, --with-ai pour le fallback LLM réel)
  run_normalization_stress_test.py   — stress test structurel (~450 URLs synthétiques)
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
python -m evaluation.run_scripts.run_normalization_eval --with-ai    # coûte des tokens Groq réels
python -m evaluation.run_scripts.run_normalization_stress_test       # stress test structurel
```

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
- `judge.py` n'utilise pas `GroqClient.structured_chat()` (modèle figé sur
  `settings.GROQ_MODEL`) mais pilote directement son client OpenAI SDK
  sous-jacent pour pouvoir cibler un modèle différent du pipeline.
