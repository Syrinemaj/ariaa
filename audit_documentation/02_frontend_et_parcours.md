# 02 — Interface utilisateur et frontend

## 1. Organisation des dossiers (`frontend/src/`)

```
pages/        21 écrans (un fichier par route)
components/   aria/, automation/, dashboard/, layout/ — composants partagés
contexts/     AuthContext, RunContext, ThemeContext, ToastContext
lib/          clients HTTP par domaine (pas de dossier api/ — le nommage réel est lib/*Api.ts)
hooks/        useHarAnalysis.ts (seul hook personnalisé recensé)
types/        définitions TypeScript partagées
```
Point d'entrée : `frontend/src/main.tsx` → monte `<App />` dans `BrowserRouter` (React Router v6). `frontend/src/App.tsx` définit l'arbre de providers (`ThemeProvider > AuthProvider > RunProvider > ToastProvider`) et la table de routes, protégée par un composant `ErrorBoundary` de classe (affiche la pile d'erreur et un bouton de retour au login en cas d'exception de rendu).

## 2. Parcours utilisateur réellement câblés (extrait de `App.tsx`)

| Route | Page | Accès |
| --- | --- | --- |
| `/login`, `/signup`, `/forgot-password`, `/reset-password`, `/auth` | `AuthPage`, `SignUpPage`, `ForgotPasswordPage`, `ResetPasswordPage`, `LoginPage` | Public |
| `/dashboard`, `/runs`, `/endpoints`, `/reports` | `DashboardPage`, `RunsHistoryPage`, `EndpointsPage`, `ReportsPage` | Tout rôle authentifié |
| `/analysis`, `/workflows`, `/openapi`, `/rag`, `/automation`, `/automation-list`, `/bulk` | pages correspondantes | `ADMIN` + `OPERATOR` (`RequireRole`) |
| `/approvals`, `/users`, `/audit-log`, `/governance`, `/connections` | pages correspondantes | `ADMIN` uniquement |
| toute autre route | — | redirigé vers `/login` |

Le contrôle d'accès par rôle est appliqué côté client par `components/layout/RequireRole.tsx` (non lu en détail — **à vérifier** : ce composant bloque-t-il le rendu ou seulement la navigation, et existe-t-il une seconde vérification côté serveur pour chaque route API correspondante — voir `app/auth/dependencies.py::require_admin` / `require_admin_or_operator`, qui confirme que le contrôle existe bien aussi côté backend).

Les 21 pages existent toutes comme fichiers réels et sont toutes routées — aucun écran mort ou orphelin détecté dans `App.tsx`. Ce document ne permet pas d'affirmer que chaque page est *fonctionnellement complète* (formulaires branchés, gestion d'erreur réelle) : seul un examen page par page le confirmerait, non réalisé exhaustivement dans cet audit. **À VÉRIFIER individuellement si une description plus fine que page-par-page est nécessaire pour le rapport.**

## 3. Authentification côté frontend

`contexts/AuthContext.tsx` implémente le cycle de connexion :
- `POST /auth/login` (`fetch` direct, pas de bibliothèque HTTP tierce) ; en cas de succès, `access_token` et `refresh_token` sont stockés dans `sessionStorage` (explicitement commenté dans le code : isolé par onglet, pour que deux onglets puissent représenter deux sessions différentes) ;
- un second appel `GET /auth/me` avec l'en-tête `Authorization: Bearer <token>` récupère le profil utilisateur affiché dans l'UI ;
- `logout` appelle `POST /auth/logout` puis vide `sessionStorage`.

Aucune bibliothèque de requêtes (React Query, Axios, SWR) n'est utilisée : chaque fichier de `lib/*Api.ts` encapsule ses propres appels `fetch`. Le détail du rafraîchissement automatique de token (intercepteur sur 401, utilisation de `refresh_token`) n'a pas été vérifié dans ce passage — **à vérifier** dans `lib/api.ts`.

## 4. Bibliothèques UI et visualisation

- **Style** : TailwindCSS (`tailwindcss@3.4.15`), classes utilitaires, pas de bibliothèque de composants (pas de shadcn/MUI/Ant détectée dans `package.json`).
- **Icônes** : `lucide-react`.
- **Graphiques** : `recharts` (utilisé vraisemblablement dans `components/dashboard/` et `ReportsPage` — **à vérifier** le détail des graphiques réellement rendus).
- **Diagrammes** : `mermaid` — présence confirmée dans les dépendances ; usage réel (rendu de diagrammes de workflow ?) non vérifié dans ce passage.

## 5. Gestion des erreurs et des états de chargement

- Erreurs de rendu React : capturées globalement par l'`ErrorBoundary` de `App.tsx`.
- Erreurs réseau/API par page : gérées individuellement dans chaque fichier `lib/*Api.ts` et chaque page — **non auditées exhaustivement**, pattern à confirmer (toasts via `ToastContext`, états `isLoading`/`error` locaux).
- `ToastContext.tsx` suggère un mécanisme de notification transverse pour les succès/erreurs d'action (ex. après une soumission de formulaire) — **à vérifier** son câblage réel dans chaque page.

## 6. Éléments non confirmés / à compléter

- Contenu détaillé de chaque formulaire (validation côté client, champs requis) — **NON AUDITÉ** dans ce document, à faire page par page si le rapport l'exige.
- Comportement exact de `RequireRole` (redirection vs message d'erreur) — **À VÉRIFIER**.
- Mécanisme de rafraîchissement de token côté client (`lib/api.ts`) — **À VÉRIFIER**.
- Tests frontend : aucun répertoire de test frontend (`*.test.tsx`, `__tests__/`, configuration Vitest/Jest) n'a été identifié dans `frontend/` lors de l'exploration de premier niveau — **à confirmer explicitement** avant d'affirmer dans le rapport qu'aucun test frontend n'existe (voir `09_tests_et_benchmarks.md`).
