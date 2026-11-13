# T10 — Chronométrage de bout en bout

- Date (UTC) : 2026-11-12 | Commit : `52c6a7f`
- **Écart assumé par rapport au protocole initial** : une seule exécution réelle par taille de HAR a été mesurée (pas 3), sans distinction cache froid/chaud, faute de temps dans cette passe. Les valeurs ci-dessous sont **réelles et mesurées**, pas estimées — mais sur un échantillon de taille 1, à ne pas interpréter comme une moyenne statistiquement stable.
- Graphique : `evaluation/results/report/e2e_timing.png` (barres horizontales, niveaux de gris, libellés en français — HAR « gros » uniquement, le point de données le plus complet).

## Méthode de mesure par étape

| Étape(s) du brief | Méthode | Pourquoi |
|---|---|---|
| 1. Upload HAR | Chemin HTTP réel (`POST /upload/har/analyze`), chronométré de bout en bout | Mesurable directement |
| 2–7 (parsing → embeddings) | Chemin asynchrone réel (tâche Celery), chronométré par **polling de `/jobs/{job_id}`** du dépôt jusqu'à `completed` | **Confirmé impossible à décomposer plus finement** sans modifier `app/` — ni la table `llm_calls`, ni Redis, ni Prometheus n'enregistrent de jalon intermédiaire entre ces sous-étapes (vérifié en Phase 0) |
| 8–10 (intention + RAG + jugement + génération du plan) | Chemin HTTP réel (`POST /automation/plan`), un seul appel englobant les trois | Ces trois sous-étapes se produisent dans un seul appel serveur ; même limite de granularité que ci-dessus |
| 11 (contrôle de gouvernance) | Non mesuré séparément | Fonction pure en mémoire (`check_execution_policy`, confirmé en T7), sans E/S — durée non significative (sub-milliseconde), noyée dans la latence réseau de n'importe quel appel qui l'englobe |
| 12 (dry-run) | Chemin HTTP réel (`POST /bulk/dry-run`, lot de 100 lignes) | Mesurable directement |
| 13 (approbation ADMIN) | **Non mesuré** | Nécessite une interaction humaine réelle (décision d'approbation) ; hors périmètre d'un chronométrage automatisé fidèle |
| 14 (exécution réelle) | **Non mesuré** | Bloqué par le garde-fou SSRF contre la cible locale `absence-app` (voir T8) — comportement correct du garde-fou, pas un défaut |
| 15 (exécution en masse 100 lignes) | **Non mesuré** (réel) ; estimation du système lui-même disponible | Même blocage SSRF ; le dry-run rapporte une estimation système de 10,0 s pour 100 appels réels au débit plafond (10 req/s) — une projection, pas une mesure |

## Résultats mesurés (HAR « gros », hr-rich-client/Sopra HR, 83 endpoints, 1 exécution)

| Étape | Durée | % du temps total mesuré |
|---|---|---|
| 1. Upload HAR | 10,12 s | 12,7 % |
| 2–7. Pipeline asynchrone complet | 66,34 s | 83,0 % |
| 8–10. Intention + RAG + jugement + plan | 2,89 s | 3,6 % |
| 12. Dry-run bulk (100 lignes) | 0,20 s | 0,2 % |
| **Temps total mesuré (HAR → catalogue prêt + un cycle de plan + dry-run)** | **79,55 s** | 100 % |

## Résultats mesurés (HAR « petit » et « moyen », 1 exécution chacun)

| HAR | Upload | Pipeline asynchrone (2–7) | Endpoints produits |
|---|---|---|---|
| petit (`example_api_traffic.har`, 7 appels) | 0,20 s | 8,65 s | 6 |
| moyen (`mock_traffic.har`, 16 appels) | 0,17 s | 8,38 s | 15 |

**Observation** : le pipeline asynchrone (étapes 2–7) ne descend quasiment jamais sous ~8,4 s, même pour un HAR trivial (6 endpoints) — l'essentiel de ce plancher est probablement la latence réseau incompressible des appels Bedrock (enrichissement + embeddings, un appel chacun par endpoint, plus un appel de regroupement en workflows), pas le volume de données traité. Le gros HAR (83 endpoints, ~14× plus d'endpoints que le petit) ne prend que ~7,7× plus de temps (66,3 s vs 8,65 s) — signe que la concurrence des appels IA (`_AI_ENRICHMENT_CONCURRENCY=8`, confirmée dans le code) amortit effectivement le coût par endpoint plutôt que de l'additionner linéairement.

## Les 3 étapes les plus lentes et leur cause probable

1. **Pipeline asynchrone (2–7), 66,3 s sur le gros HAR** — cause la plus probable : le volume d'appels Bedrock (96 arbitrages de zone grise + 83 enrichissements + 83 embeddings + clustering de workflows, soit plus de 250 appels réseau vers Bedrock au total), partiellement parallélisés mais dominés par la latence réseau cumulée. **Hypothèse, non démontrée par une décomposition fine** (confirmé impossible sans modifier `app/`).
2. **Upload du gros HAR, 10,1 s** — cause probable : transfert réseau d'un fichier de 62,1 Mo vers l'API, plus son écriture sur disque avant mise en file Celery. Hypothèse cohérente avec le fait que les petits/moyens HAR (quelques dizaines de Ko) s'uploadent en ~0,2 s.
3. **Génération du plan (8–10), 2,89 s** — cause probable : un appel Bedrock pour l'analyse d'intention, un appel d'embedding pour la requête RAG, un appel au juge de pertinence, et un appel de génération du plan — jusqu'à 4 appels réseau séquentiels dans le pire cas. Hypothèse, non décomposée.

## Résultats mesurés (HAR `absence.har`, application réelle locale utilisée en T8/Gouvernance/SSRF, 1 exécution)

Mesuré après coup (2026-11-12), en réutilisant le même fichier `absence.har` que celui déjà actif dans ARIA tout au long de cette campagne (T8, captures Gouvernance/Approvals/SSRF), pour ancrer la figure `e2e_timing.png` sur l'application réellement ciblée plutôt que sur un HAR tiers.

| Étape | Durée | Détail |
|---|---|---|
| 1. Upload HAR | 0,98 s | Fichier de 1,67 Mo, 462 entrées HAR brutes |
| 2–7. Pipeline asynchrone complet | 42,77 s | 379 appels API nettoyés → 18 endpoints finaux, 5 workflows (`authentication_session`, `employee_management`, `request_management`, `balance_management`, `uncategorized_calls`) |
| 8–10. Intention + RAG + jugement + plan | 2,94 s | Instruction « Retrieve the list of all employees », confiance 0,85, 1 étape retenue (`GET /api/employees`) |
| **Total mesuré** | **46,69 s** | |

**Observation** : ce run produit un nombre d'endpoints finaux proche du HAR « moyen » (18 contre 15) mais avec un pipeline asynchrone 5 fois plus long (42,77 s contre 8,38 s). Le volume d'appels bruts avant déduplication (379 contre 16) est en revanche très supérieur — cohérent avec l'hypothèse déjà formulée que c'est le volume de trafic brut à classer/arbitrer (et donc le nombre d'appels Bedrock déclenchés), plus que le nombre d'endpoints finaux, qui détermine la durée du pipeline. Hypothèse, non décomposée finement (même limite que ci-dessus).

## Incident réel rencontré pendant cette mesure (worker Celery)

Une première tentative sur ce même fichier (job `082f1c87-3325-400d-9521-8c1f670cc3ef`) a provoqué un **crash réel du worker Celery** (`WorkerLostError: Worker exited prematurely: signal 11 (SIGSEGV)`), vraisemblablement pendant un appel Bedrock. La **nouvelle tentative automatique de Celery a silencieusement échoué à refaire le travail** : le verrou de déduplication (`task_lock:...`) posé par la tentative plantée était toujours détenu, donc le retry s'est contenté de le constater et de retourner `None` en se déclarant « succeeded » (`succeeded in 0.12s: None`) sans jamais relancer le pipeline. Conséquence : le job est resté bloqué indéfiniment en `status: "processing"`, sans mécanisme permettant au client (ou à l'opérateur) de détecter l'échec autrement que par un timeout côté appelant.

**Découverte de fiabilité** : en cas de crash du worker pendant une tâche verrouillée par déduplication, le verrou n'est pas libéré et aucun état d'échec n'est propagé au job — un job peut donc rester bloqué en "processing" de façon permanente après un crash, invisible pour l'utilisateur tant qu'il ne timeout pas côté client. Contournement utilisé ici : nouvel upload (nouveau `file_id`/verrou), qui a abouti sans incident. Aucune modification du code (`app/`) n'a été faite pour cette campagne de mesure ; ce constat est fait par observation du comportement réel, pas par relecture du code.

## Limites de cette mesure

- Échantillon de taille 1 par HAR (pas 3 répétitions), aucune distinction cache froid/chaud.
- Étapes 13 (approbation), 14 (exécution réelle) et 15 (exécution en masse réelle) non mesurées, bloquées par le garde-fou SSRF (T8) ou nécessitant une interaction humaine.
- Les causes des étapes lentes sont des hypothèses argumentées, explicitement non démontrées par une instrumentation fine — comme requis.
- Le run `absence.har` ci-dessus est une mesure complémentaire ajoutée après la campagne initiale, sur un seul essai réussi (après un essai en échec dû à un crash infrastructure, documenté ci-dessus) — mêmes réserves de taille d'échantillon que le reste de ce document.
