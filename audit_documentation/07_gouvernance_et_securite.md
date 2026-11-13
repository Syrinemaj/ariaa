# 07 — Gouvernance, validation, gestion des risques et sécurité

## 1. Moteur de gouvernance

`app/governance/policy_engine.py::check_execution_policy` — fonction pure confirmée (pas d'accès réseau/BD dans la fonction elle-même ; les données `policy`/`forbidden_rules` lui sont passées en argument par l'appelant, voir §3).

Trois décisions possibles, confirmées littéralement dans le code : `ALLOW`, `REQUIRE_APPROVAL`, `BLOCK`, avec une sévérité ordonnée `_SEVERITY = {ALLOW: 0, REQUIRE_APPROVAL: 1, BLOCK: 2}`. Le commentaire d'en-tête du module énonce explicitement la règle de non-contournement : *« A BLOCK can NEVER be downgraded by admin approval »*.

Ordre de vérification confirmé dans le code :
1. **Règles d'endpoints interdits** (`_check_forbidden_rules`) ;
2. **Politique d'environnement** (`_check_environment_policy`) : absence de politique configurée pour un environnement → `BLOCK` (*"failing closed"*, texte littéral du code) ; mode `forbidden` → `BLOCK` ; mode inconnu → `BLOCK` (*"failing closed"* également) ; sinon selon le mode (`full_access` → `ALLOW`, etc.) ;
3. **Seuil de risque numérique** (`_check_risk_threshold(risk_score, risk_threshold_low, risk_threshold_high)`) : `risk_score <= low` → `ALLOW` ; `risk_score > high` → `BLOCK` ; sinon → `REQUIRE_APPROVAL`.

## 2. Score de risque

`app/governance/scoring.py::compute_plan_risk_score(plan)` = **maximum** (pas moyenne) des scores de toutes les étapes du plan — confirmé littéralement, avec le commentaire explicite : *« one high-risk step makes the whole plan high-risk; it is not diluted by averaging »*. Barème : `RISK_LEVEL_SCORES = {"low": 1, "medium": 5, "high": 10}`. Une valeur de `risk_level` inconnue (ne devrait jamais arriver, `_risk_level` n'en produit que trois) est traitée comme `"high"` par sécurité (*"fails closed rather than silently ALLOWing"*). Le niveau par étape (`low`/`medium`/`high`) vient de `app/planner/plan_builder.py::_risk_level(method, quantity)` (méthode HTTP + volume).

## 3. Seuils et politiques par défaut (vérifiés dans le modèle de données)

`app/models/governance.py::GovernancePolicy` — singleton par organisation :
- `risk_threshold_low: int = 1`, `risk_threshold_high: int = 10` (défauts confirmés dans la colonne SQLAlchemy) ;
- `DEFAULT_ENVIRONMENT_POLICIES = {"test": "full_access", "preprod": "full_access", "prod": "full_access"}` — confirmé littéralement : **les trois environnements, y compris la production, démarrent en accès complet par défaut**, sans distinction ; une organisation qui ne reconfigure pas explicitement sa politique a donc une production aussi ouverte que son environnement de test.

## 4. Règle spécifique à l'exécution en masse (vérifiée précisément)

`app/api/bulk.py::_resolve_bulk_governance_and_approval` :
```python
needs_approval = policy_result.decision == REQUIRE_APPROVAL or current_user.role != UserRole.ADMIN
```
Formulation exacte, plus précise qu'un résumé général : un **administrateur** qui lance une exécution en masse n'a besoin d'approbation que si la politique de gouvernance l'exige elle-même (`REQUIRE_APPROVAL`) ; un **opérateur** (`role != ADMIN`) a **toujours** besoin d'une approbation admin pour une exécution réelle en masse, quelle que soit la décision de gouvernance — le commentaire du code justifie ceci par un rayon d'impact plus large qu'une automatisation simple (une seule approbation couvre N lignes). Le flux d'approbation réutilise le même mécanisme que l'automatisation simple (création d'un `AutomationRun`/`AutomationApproval` en `pending_approval`, interrogé ensuite par le frontend via `GET /approvals`).

## 5. Authentification et autorisation

- **JWT** : `python-jose` (`app/auth/jwt.py`), algorithme `HS256` (`app/core/config.py::JWT_ALGORITHM`), expiration access token 30 min, refresh token 30 jours (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`). `JWT_SECRET_KEY` validé au démarrage (≥ 32 octets, levée d'exception sinon) — **opérationnel**.
- **Rôles** : exactement deux, `UserRole.ADMIN` et `UserRole.OPERATOR` (`app/models/user.py`) — pas de rôle intermédiaire. Dépendances FastAPI confirmées : `require_roles`, `require_admin`, `require_admin_or_operator` (`app/auth/dependencies.py`) — **opérationnel**, et doublé côté frontend par `RequireRole` (voir `02_frontend_et_parcours.md`).
- **Hachage de mot de passe** : `passlib.CryptContext(schemes=["bcrypt"])` (`app/auth/password.py`) — **opérationnel**.
- **Jetons de rafraîchissement** : table `refresh_tokens` avec `ForeignKey("users.id", ondelete="CASCADE")` (`app/models/refresh_token.py`) — **opérationnel**.

## 6. Protection SSRF et sécurisation des requêtes sortantes

- `app/security/ssrf_guard.py::validate_target_url` + `app/security/pinned_dns_transport.py` — confirmés : résolution DNS validée contre les réseaux interdits (`_is_forbidden_ip`, adresses privées/boucle locale/métadonnées cloud), puis **épinglage** de l'adresse résolue pour toute la durée de la connexion HTTP via une sous-classe `PinnedDNSTransport(httpx.AsyncHTTPTransport)` — empêche une reliaison DNS malveillante entre validation et appel réel. **Opérationnel.**
- `app/core/config.py::ALLOW_HTTP_TARGETS` (défaut `False`) — commentaire explicite : *"NEVER enable in production"*. `ALLOWED_TARGET_DOMAINS` configurable en liste blanche.
- Protection anti-traversée de chemin et validation de cohérence d'hôte dans `app/automation/executor.py` — voir `06_execution_et_bulk.md` §2. **Opérationnel.**

## 7. Gestion des secrets de connexion

`app/connections/crypto.py` — confirmé : chiffrement symétrique **Fernet**, clé lue depuis la variable d'environnement `CONNECTION_ENCRYPTION_KEY` (validée au démarrage comme clé Fernet valide), fonctions `encrypt_secret`/`decrypt_secret`. Le déchiffrement n'intervient que côté worker au moment de l'exécution réelle (confirmé par la présence de `get_decrypted_secret_for_execution` citée dans un document antérieur — fonction non relue littéralement dans ce passage, **à vérifier** son emplacement exact si une citation de ligne est requise). **Opérationnel** pour le chiffrement au repos ; **absent** pour un véritable flux OAuth 2.0 client-credentials (le type `oauth_client_credentials` produit le même en-tête `Authorization: Bearer` que `service_account`, sans échange de jeton — à confirmer par relecture directe de `app/connections/service.py::build_auth_headers`, non refaite intégralement dans ce passage mais cohérente avec le modèle `auth_type` à 3 valeurs observé).

## 8. Rate limiting

`app/core/rate_limit.py` — `slowapi.Limiter` avec backend Redis partagé entre workers (commentaire explicite : *"un seul compteur partagé entre TOUS les workers"*). Deux instances : `limiter` (par défaut, clé = adresse IP via `get_remote_address`) et `limiter_by_user`. Valeurs par défaut confirmées dans `app/core/config.py` : `RATE_LIMIT_DEFAULT="100/minute"`, `RATE_LIMIT_AUTH="5/minute"`, `RATE_LIMIT_UPLOAD="10/hour"`, `RATE_LIMIT_EXECUTE="5/minute"`. Appliqué dans `app/main.py` via `_rate_limit_exceeded_handler`. **Opérationnel.**

## 9. CORS

`CORSMiddleware` monté dans `app/main.py`, origines autorisées lues depuis `CORS_ORIGINS` (`app/core/config.py`, défaut `http://localhost:5173`). **Opérationnel**, configuration de développement par défaut (une seule origine locale) — **à vérifier** la configuration réelle utilisée en production (`.env.prod`, non lu — secret/configuration d'environnement, hors périmètre de cet audit).

## 10. Protection des données sensibles dans les logs / sanitisation

Voir `03_pipeline_har.md` §8 et `06_execution_et_bulk.md` §7 : `app/security/sanitizer.py::sanitize_payload` masque les clés sensibles (`authorization`, `cookie`, `password`, `token`, `api_key`, `secret`...) — **opérationnel mais uniquement au moment de la journalisation d'une exécution**, pas au moment de l'ingestion d'un fichier HAR brut (lacune confirmée, à traiter comme CRITIQUE dans le tableau des manques).

## 11. Validation des entrées / protection contre les injections

`app/security/payload_validator.py`, `app/security/business_payload_rules.py` — présence confirmée ; contenu détaillé (type de validation : JSON Schema, règles métier spécifiques) non audité ligne à ligne dans ce passage. **À VÉRIFIER** avant toute affirmation précise dans le rapport (ex. protection explicite contre l'injection SQL — l'usage généralisé de SQLAlchemy avec requêtes paramétrées est la protection structurelle de facto, mais aucune validation additionnelle spécifique « anti-injection SQL » n'a été localisée nommément).

## 12. Isolation multi-organisation (tenancy)

`app/security/tenancy.py` — présence confirmée, cohérente avec les mixins `OrgScopedMixin` observés sur la quasi-totalité des modèles (`app/models/*.py`). Mécanisme exact (filtrage automatique par requête vs vérification manuelle à chaque endpoint) non audité en détail dans ce passage — **à vérifier**.
