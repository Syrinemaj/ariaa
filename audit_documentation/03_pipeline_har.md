# 03 — Importation et traitement des fichiers HAR

## 1. Importation

Routes : `POST /upload/har`, `POST /upload/har/normalized`, `POST /upload/har/analyze` (`app/api/upload.py`). La dernière retourne `202 Accepted` (`AnalyzeJobResponse`), confirmant un traitement asynchrone délégué à Celery (file `ingestion`, `app/workers/tasks/ingestion.py` — **contenu détaillé non relu dans cet audit, à vérifier si des informations précises sur le déroulement de la tâche sont nécessaires**).

Limites de taille/format : `app/security/upload_limits.py` existe dans le dépôt — son contenu précis (taille max en Mo, extensions acceptées pour un HAR) n'a pas été relu ligne à ligne dans ce passage. **À VÉRIFIER** avant de citer une valeur numérique dans le rapport (ne pas réutiliser une valeur éventuellement citée dans un chapitre antérieur sans l'avoir confirmée ici).

## 2. Parsing

`app/ingestion/har_parser.py::parse_har_file` transforme le JSON HAR en une liste de `TrafficEntry` (`app/ingestion/models.py`). Champs extraits par entrée (déduits de la signature de `make_entry`/`TrafficEntry` observée dans `tests/unit/test_heuristic_filter.py`) : `method`, `url`, `path`, `status`, `mime_type`, `request_headers`, `response_headers`, `request_body`, `response_body`.

## 3. Filtrage dur (règles, sans IA)

`app/ingestion/traffic_cleaner.py::clean_traffic` élimine, avant tout scoring :
- ressources statiques (extension/MIME),
- domaines de télémétrie connus,
- méthodes `OPTIONS`/`HEAD`,
- chemins d'infrastructure (`/health`, `/favicon.ico`...),
- entrées de statut `0` (requête annulée côté navigateur, convention HAR).

Liste exacte des domaines de télémétrie (nombre exact, « treize » cité dans un document antérieur) — **à recompter précisément dans `traffic_cleaner.py` avant de republier ce chiffre** ; non reconfirmé indépendamment dans ce passage d'audit.

## 4. Score combiné et seuils de décision

Deux fonctions indépendantes, combinées par `app/ingestion/noise_scoring.py::score_entries` :

- **Score heuristique** — `app/ingestion/heuristic_filter.py::compute_heuristic_score`. Formule exacte, lue directement dans le code :

  ```
  score = 0.0
  + 0.25 si method ∈ {POST, PUT, PATCH, DELETE}
  + 0.05 si method == GET
  + 0.25 si has_structured_content(entry)   # JSON, ou XML/SOAP (legacy servlet)
  + 0.15 si has_api_hint(path)              # "/api/", "/graphql", "/rest/", "/v1/".."/v3/", "/backend/", "/services/", "/cxf/", "servlet"
  + 0.10 si 200 <= status < 400
  score = min(score, 1.0)
  ```

  Ces poids (+0.25 contenu, +0.15 indice d'URL) sont le résultat documenté d'une **recalibration mesurée** : le docstring de la fonction indique explicitement les valeurs d'origine (+0.35 contenu, +0.25 URL), la mesure contre `evaluation/golden_dataset/traffic_classification_golden_dataset.json` (30 cas), et l'effet chiffré (précision 0.643 → 0.667, F1 0.783 → 0.800, faux positifs 10 → 7, rappel inchangé à 1.000). Un script d'évaluation réel existe pour reproduire cette mesure : `evaluation/run_scripts/run_traffic_classification_eval.py` + `evaluation/metrics/traffic_classification_metrics.py`. Ce point est donc traçable et vérifié — contrairement à d'autres métriques citées ailleurs dans le dépôt (voir `09_tests_et_benchmarks.md`, discordance sur la comparaison de modèles d'embedding).

- **Score de charge utile** — `app/ingestion/payload_classifier.py::compute_payload_score`, fondé sur un ensemble fixe de mots-clés métier (`BUSINESS_KEYWORDS`, ~40 termes FR/EN : employee, invoice, payment, conge, matricule, paie, collaborateur...), recherchés dans le chemin et le corps aplati (requête + réponse) en minuscules, sans contrainte de position (un mot-clé trouvé n'importe où dans une valeur compte, pas seulement comme nom de champ — limite documentée dans le code et confirmée ici).

- **Seuils de décision** (`app/ingestion/noise_scoring.py`) : `LOW_THRESHOLD = 0.30`, `HIGH_THRESHOLD = 0.70`. Score combiné ≥ 0.70 → conservé par les règles ; ≤ 0.30 → rejeté par les règles ; entre les deux → zone grise, arbitrage IA.

## 5. Arbitrage par IA (zone grise uniquement)

`app/ingestion/semantic_filter.py` (fonction `semantic_filter_with_azure` — nom resté de l'époque où un fournisseur Azure OpenAI existait dans le projet ; le client réellement injecté est désormais toujours un `BedrockClient`, voir `app/core/config.py::AI_PROVIDER` et son commentaire sur la suppression de `GroqClient`/`AzureOpenAIClient`). Le modèle effectivement utilisé est `amazon.nova-lite-v1:0` (configuration globale `BEDROCK_MODEL`), appelé uniquement pour les entrées en zone grise — pas de modèle dédié distinct identifié pour cette étape précise.

## 6. Normalisation des URL et paramètres

Cascade en trois mécanismes, vérifiée dans le code :
1. **Motifs** (`app/normalization/parameter_detector.py::detect_parameter_type`) : ensemble de regex (entier, UUID, JWT, date, identifiants métier nommés, hash, préfixes type Stripe `ch_`/`sub_`/`cus_`/`inv_`/`pi_`/`pm_`/`re_`/`po_`/`tr_`/`prod_`, chacun avec une confiance propre — ex. 0.92 pour `ch`/`sub`/`cus`/`inv`/`pi`/`pm`, 0.90 pour `re`/`po`/`tr`/`prod`). Segments statiques connus (`v1`...`v20`, `latest`, `beta`, `me`, `self`) exclus avant tout motif.
2. **Statistique inter-requêtes** (`app/normalization/dynamic_segment_detector.py::detect_dynamic_positions`) : comparaison par point fixe itératif (commentaire du code : *"Iterative fixed point: repeatedly compare all pairs of segment lists..."*) ; exclusion explicite d'une position suivant immédiatement un segment de version/environnement connu — corrige un bug documenté dans le code lui-même (`/api/v1/{v1_id}` fabriqué par une version antérieure, cité littéralement dans le commentaire source).
3. **Regroupement par LLM** (`app/normalization/group_normalizer.py`) : seuil de confiance `_CONFIDENCE_THRESHOLD = 0.70`, scores de confiance de groupe `{"high": 0.90, "medium": 0.75}` — valeurs confirmées dans le code, cohérentes avec la description d'un document antérieur.

Nommage du paramètre : `parameter_detector.py::infer_parameter_name`, cascade confiance → nom de champ observé dans le corps (0.95) → table de préfixes connus (0.90–0.92, valeurs listées ci-dessus) → segment précédent singularisé → repli générique.

## 7. Endpoints multiplexés et déduplication

- `app/ingestion/action_discriminator.py::detect_action_discriminator_field` — détection structurelle (forme du corps, pas un nom de champ fixe) confirmée par la présence du fichier et de la fonction ; le détail interne de l'algorithme (comparaison exacte des formes) n'a pas été relu ligne à ligne dans ce passage. **À VÉRIFIER** si une citation plus précise que le nom de fonction est nécessaire.
- `app/ingestion/deduplication.py::deduplicate_endpoints` et `app/ingestion/query_params.py::classify_query_params` — présence confirmée ; comportement interne non relu en détail dans cet audit, **À VÉRIFIER**.

## 8. Sanitisation des données sensibles au moment de l'ingestion

**NON IDENTIFIÉ DANS LE CODE.** Recherche explicite (`grep "sanitiz"` dans `app/ingestion/` et `app/normalization/`) : aucune occurrence. Le seul mécanisme de masquage du dépôt, `app/security/sanitizer.py::sanitize_payload`, n'est appelé que par `app/automation/service.py` et `app/bulk_execution/batch_executor.py` — c'est-à-dire au moment de journaliser les résultats d'une **exécution** (table `AutomationStepLog`), jamais au moment où un fichier HAR brut est parsé, nettoyé ou stocké. Un fichier HAR contenant des cookies, jetons ou données personnelles réelles est donc conservé tel quel à ce stade du pipeline. C'est un point CRITIQUE à faire remonter dans le tableau des manques.

## 9. Gestion des erreurs

**NON AUDITÉ en détail** dans ce passage (codes d'erreur retournés par `app/api/upload.py` en cas de HAR malformé, fichier trop volumineux, etc.) — à compléter si nécessaire.
