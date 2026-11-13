# T1 — Tests unitaires + couverture

- Date (UTC) : 2026-11-11T23:33:07.172030+00:00
- Commit : `52c6a7f42e586271020ce14187956cbd79018712`
- Commande : `pytest tests/unit --cov=app --cov-report=term-missing --cov-report=json:evaluation/results/report/t1_coverage.json --junitxml=evaluation/results/report/t1_junit.xml -q`
- Total collecté : 475 | Réussis : 444 | Échoués : 0 | Ignorés : 31
- Couverture globale (tout `app/`) : 41.3 %

| Module | Lignes couvertes | Lignes totales | Couverture |
|---|---|---|---|
| ingestion | 98 | 261 | 37.5 % |
| normalization | 591 | 768 | 77.0 % |
| rag | 137 | 323 | 42.4 % |
| planner | 231 | 309 | 74.8 % |
| governance | 91 | 146 | 62.3 % |
| approval | 0 | 31 | 0.0 % |
| automation | 136 | 336 | 40.5 % |
| bulk_execution | 104 | 296 | 35.1 % |
| security | 133 | 286 | 46.5 % |
| connections | 60 | 185 | 32.4 % |
