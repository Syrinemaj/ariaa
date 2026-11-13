# T3 — Entonnoir du pipeline sur 3 fichiers HAR réels

- Date (UTC) : 2026-11-11T23:53:52Z | Commit : `52c6a7f`
- Modèle LLM : `amazon.nova-lite-v1:0` (défaut de production)
- **Note importante** : `app/ingestion/semantic_filter.py` ne journalise jamais dans la table `llm_calls` (aucun appel à `log_llm_call_and_print_terminal_summary`). Le coût réel de l'arbitrage IA de ce module n'est donc **pas mesurable** directement — la colonne coût ci-dessous est une **estimation** extrapolée depuis `evaluation/results/summary_traffic_classification.json` (0,0019 $ / 30 appels Nova Lite sur une tâche de classification comparable ≈ 0,0000634 $/appel), pas une valeur observée.

| HAR | Brutes | Filtre dur | Gardés (règles) | Rejetés (règles) | Gardés (IA) | Rejetés (IA) | Endpoints finaux | Appels LLM réels | Coût estimé |
|---|---|---|---|---|---|---|---|---|---|
| petit (`example_api_traffic.har`, 4,6 Ko) | 7 | 6 | 6 | 0 | 0 | 0 | 6 | 0 | 0 $ |
| moyen (`mock_traffic.har`, 19,9 Ko) | 16 | 16 | 16 | 0 | 0 | 0 | 15 | 0 | 0 $ |
| gros (`foryou-hra4u-final.har`, 62,1 Mo) | 728 | 279 | 165 | 18 | 51 | 45 | **84** | **96** | ≈ 0,0061 $ |

**Résultat le plus significatif** : sur le gros HAR, les règles seules n'auraient produit que 50 endpoints après normalisation/déduplication (165 gardés par les règles → 50 endpoints distincts). Avec l'arbitrage IA sur la zone grise (96 cas, 51 récupérés), le catalogue final passe à **84 endpoints** — soit 34 endpoints métier supplémentaires (+68 %) que les règles seules auraient manqués, confirmant concrètement la valeur de l'étape d'arbitrage LLM pour ce fichier.

Export des 84 endpoints avec colonnes vides à remplir : `T3_endpoints_gros.csv` (+ `T3_endpoints_petit.csv`, `T3_endpoints_moyen.csv`).
