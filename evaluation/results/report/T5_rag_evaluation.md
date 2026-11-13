# T5 — Evaluation RAG (25 requetes, catalogue reel 83 endpoints)

- Date (UTC) : 2026-11-12T00:07:38.745059+00:00 | Commit : `52c6a7f42e586271020ce14187956cbd79018712` | run_id : `06f866a1-d8d6-4900-b3a0-cd3bc02c568c`

## Sans juge de pertinence (recherche vectorielle seule)

| | n | Recall@1 | Recall@5 | MRR |
|---|---|---|---|---|
| Global | 24 | 0.917 | 1.0 | 0.958 |
| Francais | 12 | 0.833 | 1.0 | 0.917 |
| Anglais | 12 | 1.0 | 1.0 | 1.0 |

Cas hors-catalogue (q25) traite honnetement (aucun resultat retourne) : False

## Avec juge de pertinence (chemin de production reel, /rag/search)

| | n | Recall@1 | Recall@5 | MRR |
|---|---|---|---|---|
| Global | 24 | 0.958 | 1.0 | 0.979 |
| Francais | 12 | 0.917 | 1.0 | 0.958 |
| Anglais | 12 | 1.0 | 1.0 | 1.0 |

Cas hors-catalogue (q25) traite honnetement (aucun resultat retourne) : True
