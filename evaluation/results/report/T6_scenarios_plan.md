# T6 — 8 scenarios de generation de plan (catalogue reel)

- Date (UTC) : 2026-11-12T00:09:20.557168+00:00 | Commit : `52c6a7f42e586271020ce14187956cbd79018712` | run_id : `06f866a1-d8d6-4900-b3a0-cd3bc02c568c`
- Taux de reussite correctement interprete : 7.5/8 (voir notes S3/S7 ci-dessous -- le critere binaire "rejet precoce" automatique etait trompeur pour ces deux cas)

**Note sur S7 (hors catalogue)** : classe par le script comme "rejet precoce" mais il s'agit en realite d'un **rejet tardif correct et honnete** : `NO_MATCHING_ENDPOINTS`, confiance 0.85 -- l'instruction est bien comprise, la recherche RAG est bien executee, mais aucun endpoint pertinent n'existe dans ce catalogue. C'est le comportement attendu, pas une anomalie.

**Note sur S3 (suppression)** : **vraie limite decouverte**, pas une hallucination d'endpoint (les deux endpoints retournes existent reellement). Pour "supprimer un compte utilisateur" sur un catalogue sans aucune capacite de suppression (aucun verbe DELETE), le systeme a propose `GET /cxf/bc/usermgt/connecteduser` puis `GET /cxf/bc/usermgt/disconnect` -- une substitution semantique trompeuse (deconnexion confondue avec suppression) plutot qu'un refus honnete du type NO_MATCHING_ENDPOINTS obtenu pour S7. A documenter comme limite dans la synthese.

| # | Categorie | Instruction | Nb etapes | Bulk | Gouvernance | Rejet precoce |
|---|---|---|---|---|---|---|
| S1 | creation simple | Creer un nouveau compteur de demandes de taches | 1 | False | REQUIRE_APPROVAL | False |
| S2 | lecture | Recuperer le plan du site | 1 | False | ALLOW | False |
| S3 | suppression (negatif -- pas de DELETE dans ce catalogue) | Supprimer le compte d'un utilisateur du systeme RH | 2 | False | ALLOW | False |
| S4 | dependance implicite | Connecter l'utilisateur puis recuperer les informations de l'utilisateur connecte | 2 | False | REQUIRE_APPROVAL | False |
| S5 | masse (200 elements) | Mettre a jour le dossier RH de 200 employes | 1 | True | REQUIRE_APPROVAL | False |
| S6 | instruction floue | Fais quelque chose avec le systeme | - | - | - | True |
| S7 | hors catalogue | Process a credit card refund for a customer order | - | - | - | True |
| S8 | instruction en anglais | Check whether the current user session is still active | 1 | False | ALLOW | False |
