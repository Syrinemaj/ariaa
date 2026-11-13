# T2 — Tests d'intégration sur infrastructure neuve

- Date (UTC) : 2026-11-12 | Commit : `52c6a7f`
- Infra : conteneurs Docker neufs, isolés (`aria-test-postgres` port 5433, `aria-test-redis` port 6380), volumes neufs, 25 migrations Alembic appliquées à vide, détruits après le test.
- Commande : `DATABASE_URL=postgresql://aria10:aria10dev@localhost:5433/aria10 REDIS_URL=redis://localhost:6380/0 pytest tests/integration -q --junitxml=evaluation/results/report/t2_junit.xml`
- Statut du dernier run CI GitHub (`gh`/API publique, repo `Syrinemaj/ariaa`) : **0 exécution de workflow au total** — `.github/workflows/ci.yml` existe mais ne s'est jamais réellement déclenché sur GitHub (dernier push sur `main` : 2026-08-12).

## Résultat

**96 tests réussis, 10 erreurs, 0 échec** (sur 106 collectés).

## Découverte réelle — bug de test masqué par l'état de la base partagée

Les 10 erreurs ont toutes la même cause, une **vraie régression de test révélée uniquement par une base neuve** :

```
sqlalchemy.exc.IntegrityError: (psycopg2.errors.NotNullViolation)
null value in column "id" of relation "organizations" violates not-null constraint
```

`tests/integration/real_db/conftest.py::_get_or_create_default_org_sync` construit `Organization(name=settings.DEFAULT_ORG_NAME)` sans jamais fournir d'`id`. Le modèle `Organization.id` (`app/models/organization.py`) **n'a aucune valeur par défaut** (`mapped_column(String, primary_key=True)`, sans `default=`) — un `id` doit toujours être fourni explicitement par l'appelant. Sur la base de développement partagée (`aria10`), ce bug ne se voit jamais : une organisation par défaut y existe déjà d'une exécution antérieure réelle, donc `get_or_create` trouve la ligne existante et ne déclenche jamais l'INSERT fautif. Sur une base réellement neuve (comme ici), l'INSERT échoue immédiatement.

**Conséquence pratique** : la CI (`.github/workflows/ci.yml`), qui provisionne une base PostgreSQL neuve à chaque run, échouerait très probablement sur ces mêmes 10 tests si elle s'exécutait réellement — ce qui n'est jamais arrivé (0 run GitHub à ce jour), donc ce défaut n'a jamais été détecté en pratique.

**Correction nécessaire** (hors périmètre de cette mission, qui ne modifie pas `app/`/`tests/`) : fournir un `id` explicite (ex. `str(uuid4())`) lors de la création de l'organisation de démonstration dans `tests/integration/real_db/conftest.py::_get_or_create_default_org_sync`.

| Fichier de test | Résultat | Cause |
|---|---|---|
| `test_auth_integration.py` (3 tests) | Erreur | `organizations.id` NULL (fixture cassée sur base neuve) |
| `test_rbac_integration.py` (4 tests) | Erreur | idem |
| `test_reports_pagination_integration.py` (3 tests) | Erreur | idem |
| tous les autres fichiers (96 tests) | Réussi | — |
