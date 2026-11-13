# 05 — Intelligence artificielle : modèles, prompts, compréhension et génération

## 1. Fournisseurs et modèles

- **Fournisseur unique de complétion** : AWS Bedrock (`app/ai/bedrock_client.py::BedrockClient`), accédé via `boto3` (API Converse). Le code et son commentaire confirment explicitement que `GroqClient` et `AzureOpenAIClient` ont existé puis ont été supprimés après une évaluation comparative (`evaluation/aggregate.py`), et que `create_ai_client()` retourne désormais toujours un `BedrockClient` — `AI_PROVIDER` n'est conservé que pour que les champs "provider" des logs/métriques Prometheus restent cohérents.
- **Modèle par défaut** : `amazon.nova-lite-v1:0` (`app/core/config.py::BEDROCK_MODEL`). Le commentaire du fichier de configuration documente la justification chiffrée de ce choix contre `deepseek.v3.2` (ancien défaut) : score qualité pondéré quasi identique (84.9 % vs 85.1 %, écart dans le bruit), mais ~37× moins coûteux ($0.0199 vs $0.7501 sur 8 tâches) et ~2.4× plus rapide avec une latence bien plus stable (P50 1.7 s / P95 2.1 s contre P50 4.1 s / P95 63 s). Ces chiffres sont traçables à `evaluation/results/full_comparison.csv`, dont le contenu réel (vérifié dans ce passage) correspond exactement : ligne `amazon.nova-lite-v1:0` → `overall_score=0.8489`, `total_cost_usd=0.0199` ; ligne `deepseek.v3.2` → `overall_score=0.8508`, `total_cost_usd=0.7501`.
- **Modèles de secours** : **aucun mécanisme de fallback automatique vers un autre modèle n'a été identifié dans `app/ai/bedrock_client.py`** dans ce passage — à ne pas confondre avec les modèles *écartés lors de l'évaluation* (`mistral.mistral-large-2402-v1:0`, incompatible structurellement avec le `toolChoice` forcé de l'API Converse — `ValidationException` documentée dans le commentaire du code ; `moonshotai.kimi-k2.5/k3`, exclus pour timeout/IAM deny). **À VÉRIFIER** s'il existe un repli applicatif en cas d'échec Bedrock (le seul mécanisme de résilience confirmé dans le code est un *retry* sur le même modèle en cas de troncature, voir ci-dessous).
- **Modèle d'embedding** : voir `04_rag_et_recherche_semantique.md` (Cohere Embed Multilingual v3, 1024 dim).

## 2. Mécanisme d'appel structuré

`BedrockClient.structured_chat` force une sortie structurée via `toolConfig`/`toolChoice: {"tool": {"name": tool_name}}` sur l'API Converse (JSON Schema en entrée). Un *retry* existe explicitement : le code logge un message précis en cas de deuxième échec (*"after retry — likely ran out of max_tokens on internal reasoning before reaching the tool call"*), confirmant qu'un nouvel essai est tenté avant d'abandonner, avec un cap configurable (`max_tokens`, défaut `_DEFAULT_MAX_TOKENS` — valeur exacte non relue dans ce passage, **à vérifier**).

Paramètres de génération confirmés dans `app/core/config.py` :
- `LLM_STRUCTURED_TEMPERATURE = 0.15` (basse température, justifiée explicitement dans le commentaire par le besoin de scores de confiance reproductibles plutôt que de variation créative) ;
- `LLM_MAX_COMPLETION_TOKENS = 1000`, `LLM_MAX_INPUT_TOKENS = 120_000`, `LLM_HIGH_TOKEN_THRESHOLD = 5000` ;
- coûts de référence pour l'estimation/observabilité : `LLM_PROMPT_COST_PER_1K = 0.00015`, `LLM_COMPLETION_COST_PER_1K = 0.00060`.

## 3. Rôle de chaque modèle par étape (pour ne pas les mélanger)

| Étape | Fichier | Modèle appelé |
| --- | --- | --- |
| Arbitrage zone grise du nettoyage HAR | `app/ingestion/semantic_filter.py` | `amazon.nova-lite-v1:0` (client générique injecté) |
| Normalisation groupée des paramètres d'URL | `app/normalization/group_normalizer.py` | idem |
| Enrichissement sémantique d'un endpoint | `app/ai/endpoint_understanding.py::enrich_endpoint_with_ai` | idem |
| Jugement de pertinence RAG | `app/rag/relevance_judge.py::verify_relevance_async` | idem |
| Analyse d'intention métier | `app/planner/intent_analyzer.py::analyze_business_intent` | idem |
| Sélection/génération de plan | `app/planner/plan_generator.py::generate_plan_selection` | idem |
| Regroupement/nommage de workflows | `app/workflows/clustering.py` (LLM en stratégie principale) | idem |
| Description enrichie de workflow | `app/workflows/workflow_descriptor.py::generate_workflow_description` | idem |

Tous les appels passent par le même `BEDROCK_MODEL` configuré globalement — **aucune étape n'utilise un modèle différent des autres**, contrairement à ce qu'un ancien historique (Groq/Azure/DeepSeek multi-fournisseurs) pourrait laisser supposer ; ce multi-fournisseur a existé puis a été retiré (voir section 1).

## 4. Analyse d'intention — échelle de confiance (vérifiée dans le code)

`app/planner/intent_analyzer.py` définit explicitement l'échelle utilisée par le prompt système :
- 0.0–0.25 : incompréhensible, hors-sujet, ou clairement pas une action API REST (`reason="INSTRUCTION_UNCLEAR"`) ;
- 0.25–0.5 : vague ;
- 0.5–0.7 : partielle (action décrite mais entités/contexte manquants) ;
- 0.7–1.0 : claire, actionnable (`reason="OK"`).

Le prompt contient des exemples concrets littéralement présents dans le code source, par ex. *« create new employee contract with email »* → `action=create, domain=hr, entities=[employee,contract,email], confidence=0.92`. Seuil de rejet précoce côté application : `PLAN_MIN_INTENT_CONFIDENCE = 0.4` (`app/core/config.py`).

## 5. Structures JSON attendues

Chaque appel structuré est lié à un schéma JSON précis (passé à `toolConfig`) — un schéma par tâche (ex. `ENDPOINT_UNDERSTANDING_SCHEMA` cité dans un document antérieur pour l'enrichissement d'endpoint). Le contenu exact de chaque schéma n'a pas été relu intégralement dans ce passage pour toutes les étapes — **à compléter au cas par cas si le rapport doit les citer verbatim**.

## 6. Validation des réponses et gestion des erreurs

Le forçage `toolChoice` sur l'API Converse garantit structurellement une réponse conforme au schéma côté modèle (pas de JSON libre à parser/valider après coup côté application pour la forme) — c'est la raison documentée de l'incompatibilité de Mistral Large avec cette architecture (ne supporte pas `toolChoice` forcé sur sa variante Converse testée, `ValidationException`). Le *retry* observé en section 2 couvre le cas de troncature par manque de `max_tokens`, pas une validation sémantique de la réponse.

## 7. Cache

**Aucun cache de réponse LLM générique (prompt → réponse) n'a été identifié** dans `app/ai/` lors de ce passage, à l'exception du cache d'**embeddings** déjà documenté en `04_rag_et_recherche_semantique.md` (Redis 24h + cache persistant par hachage de contenu), qui ne concerne pas les appels de complétion structurée. **À VÉRIFIER** avant d'affirmer l'absence totale de cache de complétion dans le rapport.

## 8. Exemple réel de commande et sortie structurée

Les seuls exemples **littéralement présents dans le code source** (pas inventés pour cet audit) sont ceux du prompt système d'`intent_analyzer.py` cités en section 4, et l'exemple du prompt de `relevance_judge.py` cité en `04_rag_et_recherche_semantique.md` (§5, `missing_aspects=['payroll', 'badge']`). Aucun fichier de log ou de trace d'appel réel (entrée utilisateur → sortie JSON effective, horodatée) n'a été localisé dans `evaluation/` pour ces deux étapes précises — les fichiers CSV de `evaluation/results/` concernent les benchmarks de comparaison de modèles (voir `09_tests_et_benchmarks.md`), pas des traces de production.
