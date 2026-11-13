# 04 — Recherche sémantique et mécanisme RAG

## 1. Modèle d'embedding

Configuré par défaut (`app/core/config.py`) : `EMBEDDING_PROVIDER = "bedrock"`, `BEDROCK_EMBEDDING_MODEL = "cohere.embed-multilingual-v3"`, `EMBEDDING_DIMENSIONS = 1024`. Une alternative locale existe et est opérationnelle dans le code (`LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-en"`, 384 dimensions, `sentence-transformers`, sans appel réseau) mais n'est pas le mode par défaut. Le commentaire du code justifie le choix de Cohere plutôt que BGE par le support multilingue (le corpus et les requêtes utilisateur d'ARIA sont fréquemment en français, et BGE est anglais uniquement).

Un repli vers `amazon.titan-embed-text-v2:0` est documenté comme un changement d'une ligne si l'accès au modèle Cohere n'est pas activé sur le compte AWS cible (les deux produisent 1024 dimensions, donc pas de migration de schéma nécessaire).

## 2. Préparation du texte avant vectorisation

`app/rag/embeddings/builder.py::build_endpoint_embedding_text` — confirmé comme combinant résumé IA, domaine et action métier, intention de la méthode HTTP en langage naturel, et noms des champs de requête/réponse (fichier et fonction vérifiés présents ; contenu exact de l'assemblage non relu caractère par caractère dans ce passage).

## 3. Stockage et cache

- **Stockage vectoriel** : PostgreSQL + extension pgvector, colonne `embedding` sur `EndpointEmbedding` (`app/models/embedding.py`, table `endpoint_embeddings`), avec un index **HNSW** (confirmé par le commentaire d'en-tête de `app/rag/retriever.py` : *« cosine distance via pgvector HNSW »*).
- **Cache de contenu persistant** : clé SHA-256 du texte d'embedding, comparée à la valeur stockée (`app/rag/vector_store.py::index_endpoint_embedding`) — réutilise le vecteur existant si le texte n'a pas changé.
- **Cache Redis à courte durée de vie** : `app/rag/embedding_cache.py`, confirmé — `_REDIS_TTL_SECONDS = 86_400` (24 h), clé SHA-256 sur `méthode:chemin:schéma trié`, stable entre plusieurs fichiers HAR/runs.

## 4. Recherche

`app/rag/retriever.py::semantic_search_endpoints` :
- `top_k: int = 5` (défaut de la fonction) ;
- `score_threshold` : défaut de fonction `0.0`, mais la valeur réellement appliquée côté API vient de `app/rag/models.py::SemanticSearchRequest.score_threshold`, dont le défaut Pydantic confirmé est **0.35** (`Field(default=0.35, ge=0.0, le=1.0)`) ;
- distance cosinus calculée en PostgreSQL via `EndpointEmbedding.embedding.cosine_distance(...)`, triée et limitée en un seul aller-retour SQL ; score = `max(0, 1 - distance)` (conforme au commentaire du module) ;
- **embedding asymétrique** confirmé par construction : la fonction embed la requête utilisateur séparément de l'indexation des endpoints (paramètre `input_type` différent attendu côté client Bedrock Cohere — présence du mécanisme confirmée par la structure du module ; valeurs exactes `search_document`/`search_query` non re-confirmées littéralement dans ce passage, **à vérifier** dans `app/rag/embeddings/bedrock_client.py` si une citation exacte est nécessaire).

Contexte transmis en aval : `app/rag/context_builder.py::build_rag_context` — présence confirmée, contenu détaillé non relu dans ce passage.

## 5. Jugement de pertinence (reranking)

`app/rag/relevance_judge.py::verify_relevance_async` — confirmé : appel systématique (pas conditionné par le score), retourne pour chaque candidat `relevant` (booléen) et `missing_aspects` (liste des éléments demandés non couverts par les champs réels de l'endpoint). Le prompt système embarqué contient un exemple littéral cité dans le code : `missing_aspects=['payroll', 'badge']` pour un cas où ni la paie ni le badge n'existent sur l'endpoint retourné — cohérent avec l'exemple narré dans un document antérieur du projet (requête *"create a new employee with payroll and badge"*), mais ici confirmé comme présent **dans le prompt lui-même**, pas seulement comme anecdote narrative.

## 6. Paramètres configurables et leurs valeurs par défaut (vérifiés)

| Paramètre | Valeur par défaut | Fichier |
| --- | --- | --- |
| `top_k` (fonction retriever) | 5 | `app/rag/retriever.py` |
| `score_threshold` (API de recherche) | 0.35 | `app/rag/models.py::SemanticSearchRequest` |
| `PLAN_MIN_RAG_SCORE` (filtre pour la génération de plan) | 0.3 | `app/core/config.py` |
| `PLAN_MIN_INTENT_CONFIDENCE` | 0.4 | `app/core/config.py` |
| TTL cache Redis d'embedding | 86 400 s (24 h) | `app/rag/embedding_cache.py` |
| Dimensions d'embedding | 1024 (Cohere/Titan) ou 384 (BGE local) | `app/core/config.py` |

Le commentaire de `PLAN_MIN_RAG_SCORE` dans `app/core/config.py` documente une mesure empirique réelle, distincte de toute évaluation Recall@1/MRR : après la migration BGE → Cohere, un cas de correspondance claire et univoque (« se connecter » → `POST /auth/login`) a scoré ≈0.37, un cas univoque bien séparé (« create a new employee » → `POST /api/employees`) ≈0.70, et des requêtes hors-sujet (« bake a chocolate cake ») ≈0.28 au plus haut. Ce sont les seuls chiffres de performance de recherche sémantique que j'ai pu retracer directement dans un commentaire de code source, assortis d'une justification explicite de la valeur retenue (0.3, choisie entre le plafond du bruit mesuré ≈0.28 et le minimum des vrais cas mesurés ≈0.37).

## 7. Point CRITIQUE — tableau de comparaison des modèles d'embedding non traçable

Un document de ce projet (`rapport/chapitre_realisation.md`, section 4.3.3) présente un tableau comparant Cohere Embed Multilingual v3, Amazon Titan Embed Text v2 et BAAI/bge-small-en sur les métriques Recall@1 et MRR, avec une méthodologie décrite (« 12 endpoints, 17 requêtes FR/EN »). **Recherche exhaustive menée dans ce passage d'audit** (`grep -rl` sur tout le dépôt pour "recall@1", "MRR", "bge-small", "titan-embed", "embed-multilingual" dans le code) : aucun script, notebook, fichier de résultats ou jeu de données ne correspond à cette évaluation précise. Les seules occurrences de "MRR" dans le dépôt concernent une métrique différente, utilisée pour l'évaluation du **planificateur de plan** (`evaluation/metrics/planner_metrics.py`, `evaluation/run_scripts/run_planner_eval.py`), pas pour la comparaison de modèles d'embedding.

**Conclusion de l'audit sur ce point** : ce tableau de chiffres (0.733/0.867/0.467 de Recall@1, etc.) n'est **pas traçable au code actuel du dépôt** et doit être traité comme **NON IDENTIFIÉ DANS LE CODE** jusqu'à ce que le développeur produise le script ou les données sources correspondants, ou confirme qu'il s'agissait d'une mesure manuelle non versionnée. Ceci contredit la règle d'or de cet audit (« ne jamais déduire une performance depuis une configuration, ni réutiliser un chiffre non vérifiable ») et doit être signalé en priorité absolue dans le tableau des informations manquantes.

## 8. Gestion des résultats insuffisants

Lorsque `score_threshold` filtre tous les résultats, ou que `verify_relevance_async` marque tous les candidats `relevant=false`, le comportement de retour (liste vide honnête vs message d'erreur) n'a pas été vérifié ligne à ligne dans `app/api/rag.py` lors de ce passage — **à vérifier** si une citation précise du comportement HTTP est nécessaire pour le rapport.
