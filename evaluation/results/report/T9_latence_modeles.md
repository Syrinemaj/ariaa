# T9 — Latence des modèles (3 exécutions réelles, Bedrock)

- Date (UTC) : 2026-11-11/12 | Commit : `52c6a7f`
- Script : `evaluation/run_scripts/run_latency_benchmark.py --models deepseek.v3.2,amazon.nova-lite-v1:0`
- 13 appels par modèle par exécution, 3 exécutions = 78 appels au total (26 déjà comptés avant ce tour, 52 dans ce tour)

| Exécution | Modèle | Moyenne | P50 | P95 | Erreurs |
|---|---|---|---|---|---|
| 1 | DeepSeek v3.2 | 2509 ms | 2376 ms | 3595 ms | 0/13 |
| 1 | Amazon Nova Lite | 1672 ms | 1671 ms | 1784 ms | 0/13 |
| 2 | DeepSeek v3.2 | 2477 ms | 2374 ms | 3880 ms | 0/13 |
| 2 | Amazon Nova Lite | 1706 ms | 1688 ms | 1868 ms | 0/13 |
| 3 | DeepSeek v3.2 | 2456 ms | 2350 ms | 3753 ms | 0/13 |
| 3 | Amazon Nova Lite | 1768 ms | 1733 ms | 2228 ms | 0/13 |

## Agrégat sur les 3 exécutions

| Modèle | Moyenne ± écart-type | P50 moyen | P95 moyen | Erreurs totales |
|---|---|---|---|---|
| DeepSeek v3.2 | 2481 ± 22 ms | 2367 ms | 3743 ms | 0/39 |
| Amazon Nova Lite | 1715 ± 40 ms | 1697 ms | 1960 ms | 0/39 |

Amazon Nova Lite reste environ 1,45× plus rapide en moyenne, de façon stable sur les 3 exécutions (écart-type faible, 22-40 ms). Aucune erreur sur 39 appels par modèle. Échantillon toujours limité à 13 cas fixes par exécution — ne pas extrapoler à la variance en charge réelle.
