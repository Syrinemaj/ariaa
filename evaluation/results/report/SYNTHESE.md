# Synthèse — Tests mesurés pour le chapitre « Réalisation » (ARIA)

- Date (UTC) : 2026-11-12 | Commit de référence : `52c6a7f42e586271020ce14187956cbd79018712`
- Modèle LLM : `amazon.nova-lite-v1:0` (comparé à `deepseek.v3.2`) | Modèle d'embedding : `cohere.embed-multilingual-v3` (1024 dim.)
- Machine : Windows-10-10.0.26200-SP0, Intel64 Family 6 Model 165 Stepping 2
- Toutes les données personnelles ou noms d'hôte propres à Sopra HR mentionnés dans ce document et les fichiers associés sont ceux déjà présents dans le fichier HAR `hr-rich-client` fourni par l'utilisatrice pour ses propres tests ; aucune donnée n'a été partagée en dehors de l'environnement local.

## Tableau récapitulatif

| Test | Statut | Résultat clé |
|---|---|---|
| T1 — Tests unitaires + couverture | ✅ Complet | 444 réussis / 0 échec / 31 ignorés (475). Couverture globale 41,3 %. **Module `approval` à 0 % de couverture.** |
| T2 — Intégration, infra neuve | ✅ Complet | 96 réussis / 0 échec / 10 erreurs. **Bug de test réel découvert** : `organizations.id` NULL sur base vraiment neuve (masqué sur la base de dev partagée). CI GitHub : 0 exécution à ce jour. |
| T3 — Entonnoir pipeline (3 HAR) | ✅ Complet | Sur le gros HAR : 728→279→**84 endpoints** finaux (50 sans l'arbitrage IA, +68 % grâce à lui). Coût LLM estimé ≈ 0,006 $ (non mesurable directement — faille d'observabilité découverte). |
| T4 — Filtrage HAR golden dataset | ✅ Complet | Précision 0,667, rappel 1,000, F1 0,800, 7 FP — **écart nul** avec les valeurs attendues. |
| T5 — Évaluation RAG (25 requêtes) | ✅ Complet | Avec juge : Recall@1 0,958 (FR 0,917 / EN 1,0), Recall@5 1,0, MRR 0,979. **Preuve concrète que le juge est nécessaire** : le cas hors-catalogue est mal géré sans juge, géré honnêtement avec. |
| T6 — 8 scénarios de plan | ✅ Complet | 6/8 nominal ; 1 rejet honnête (hors-catalogue) ; **1 limite réelle découverte** : substitution sémantique trompeuse (« supprimer » → « déconnecter ») faute de capacité de suppression dans le catalogue. |
| T7 — Matrice gouvernance/sécurité | ✅ Complet (17/17) | Dont 1 **découverte de conception** : BLOCK par score de risque seul est inatteignable avec les seuils par défaut. Cas 5 et 11 vérifiés par inspection statique du code réel (pas de live). |
| T8 — Exécution en masse (absence-app) | ⚠️ Partiel | Upload→mapping→validation→dry-run : 100 % réels et réussis (100/100 lignes valides). **Exécution réelle bloquée par le garde-fou SSRF** (localhost explicitement interdit, comportement correct). Sous-cas (a)(b)(c) non testés en conséquence. |
| T9 — Latence des modèles (×3) | ✅ Complet | Nova Lite 1715±40 ms vs DeepSeek 2481±22 ms, 0 erreur/39 par modèle. |
| T10 — Chronométrage end-to-end | ⚠️ Simplifié | 1 exécution/HAR au lieu de 3, pas de distinction cache froid/chaud. Pipeline complet mesuré : gros HAR 66,3 s (2–7), upload 10,1 s, plan 2,89 s, dry-run bulk 0,20 s. |

## Écarts par rapport aux brouillons initiaux

- **Latence LLM** (chiffres envisagés en préparation : 9592/1776 ms, P95 63039/2092 ms) : **infirmés**, remplacés par des mesures réelles bien plus favorables et stables (voir T9). Ne jamais citer les chiffres de préparation.
- **T5/T6** : initialement prévus sur un domaine RH générique (employés/congés) ; finalement ancrés sur le **vrai catalogue** du HAR `hr-rich-client` (83 endpoints réels), plus rigoureux mais de nature différente (portail RH legacy plutôt que gestion d'absences).
- **T8** : le plan prévoyait un test complet avec idempotence/disjoncteur/409 ; seule la chaîne jusqu'au dry-run a pu être validée, l'exécution réelle étant bloquée par un mécanisme de sécurité fonctionnant correctement (pas un report de ma part, un blocage réel et légitime).
- **T10** : réduit à 1 exécution par taille de HAR (au lieu de 3×cache froid/chaud), par contrainte de temps dans cette session.

## Limites générales de cette campagne de tests

- **Échantillons réduits** : 30 cas (T4), 25 requêtes (T5), 8 scénarios (T6), 13 appels (T9) — aucun de ces chiffres ne doit être présenté comme statistiquement représentatif d'un usage en production à grande échelle.
- **Exécution unique** pour la plupart des mesures de temps (sauf T9) — pas d'écart-type calculable au-delà de T9.
- **Environnement local** : toutes les mesures reflètent une machine de développement unique (Windows, Docker local), pas un environnement de production ni une charge concurrente réelle.
- **Deux failles d'observabilité découvertes en cours de route**, utiles à mentionner dans le rapport : (1) `app/ingestion/semantic_filter.py` ne journalise jamais ses appels LLM dans la table `llm_calls` — coût non mesurable directement pour cette étape précise ; (2) aucune métrique ni journal ne permet de décomposer le pipeline asynchrone d'ingestion en ses sous-étapes (parsing, scoring, arbitrage, normalisation, enrichissement, embeddings) — seule la durée globale est observable en conditions réelles.
- **Un bug de test réel découvert** (T2) : la fixture de test d'intégration `_get_or_create_default_org_sync` échoue sur une base de données réellement neuve (NULL sur `organizations.id`), masqué jusqu'ici par l'existence d'une organisation par défaut sur la base de développement partagée — jamais détecté car la CI GitHub ne s'est jamais réellement exécutée (0 run à ce jour).

## Captures d'écran restant à faire (pour le rapport, non produites par cette campagne)

1. Catalogue d'endpoints après ingestion du HAR `hr-rich-client` (83 endpoints, page Endpoints d'ARIA).
2. Résultat d'une recherche RAG en français avec couverture partielle signalée (ex. requête q24 de T5, « statut de report de congés »).
3. Plan généré pour le scénario S3 de T6 (le cas de substitution sémantique « suppression » → « déconnexion »), pour illustrer concrètement cette limite dans le rapport.
4. Écran de validation/dry-run d'un lot bulk de 100 lignes (T8), avec le détail `ready_for_execution: true`.
5. Message d'erreur SSRF obtenu lors de la tentative d'exécution réelle de T8 (utile pour illustrer la section sécurité du rapport).

## Fichiers produits

Tous dans `evaluation/results/report/` : `T1_tests_unitaires.{json,csv,md}`, `T2_integration_infra_neuve.md` (+ `t2_junit.xml`), `T3_entonnoir_pipeline.{json,csv,md}` + `T3_endpoints_{petit,moyen,gros}.csv`, `T4_filtrage_har_golden.{json,csv,md}`, `T5_rag_evaluation.{json,md}`, `T6_scenarios_plan.{json,md}`, `T7_gouvernance_securite.{json,csv,md}`, `T8_execution_masse.md` (+ `T8_bulk_100_step1.json`), `T9_latence_modeles.md`, `T10_chronometrage_e2e.md` + `e2e_timing.png`, `SYNTHESE.md` (ce fichier). Code dans `evaluation/report_tests/`.
