# Harness d'évaluation ARIA

## Lancer l'évaluation

Doit tourner là où `settings.DATABASE_URL` est résolvable — dans ce projet
l'hôte `postgres` n'existe que sur le réseau Docker, donc depuis la machine
hôte Windows la commande échoue (`could not translate host name "postgres"`).
Lancer depuis le conteneur `aria-api` :

```bash
docker compose exec -e EVAL_MODE=true api python evaluation/run_eval.py
```

(équivalent local, si un jour l'API tourne hors Docker avec Postgres
accessible directement) :

```bash
EVAL_MODE=true python evaluation/run_eval.py
```

## Interpréter les résultats

- Hit rate > 0.7  → le RAG retrouve les bons endpoints
- MRR > 0.6       → le bon endpoint arrive en tête
- Mapping > 0.8   → le CSV→API mapping fonctionne (catégorie A)
- Faithfulness > 4/5 → pas d'hallucination d'endpoints
- Completeness > 3/5 → les étapes implicites sont détectées

## Structure

```
golden_dataset.json  — 15 cas de test (5A + 5B + 5C)
tracer.py            — instrumentation pipeline (EVAL_MODE only)
judge.py             — LLM-as-judge via Groq (modèle indépendant du pipeline)
metrics.py           — calculs hit rate / MRR / precision / conformity / mapping
run_eval.py          — harness principal + export CSV
results.csv          — généré après chaque run (gitignore)
```

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
