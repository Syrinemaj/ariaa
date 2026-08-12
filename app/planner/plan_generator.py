"""
Génération de plan par LLM, ancrée dans les endpoints récupérés par RAG.

# ARIA-RAG-FIX: build_automation_plan() transformait auparavant CHAQUE endpoint
# retourné par la recherche RAG en étape de plan, sans filtrage — rag_context
# était calculé (search_rag_context) mais jamais lu par un LLM pour décider
# lesquels de ces candidats sont réellement pertinents pour l'instruction.
# Ce module ajoute cette décision manquante : étant donné les candidats
# récupérés (rag_context) et l'instruction, le LLM sélectionne et ordonne le
# sous-ensemble d'endpoints candidats qui forme un plan cohérent. Il est
# explicitement contraint aux endpoints réellement listés (voir le prompt) —
# plan_builder.py applique en plus cette contrainte en code : n'accepte
# jamais une canonical_key hallucinée hors de l'ensemble candidat retourné
# par RAG (voir le filtrage dans build_automation_plan).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

# ARIA-WORKFLOW-V2: TYPE_CHECKING-guarded — no runtime import, so no
# circular-import risk with planner/models.py or models/workflow.py, but
# still resolvable by type checkers/IDEs (from __future__ import annotations
# above already makes every annotation in this file lazy-evaluated).
if TYPE_CHECKING:
    from app.models.workflow import WorkflowModel
    from app.planner.models import BusinessIntent

logger = logging.getLogger(__name__)

# ARIA-WORKFLOW-V2: replaces the minimal single-purpose prompt with a fuller
# spec (chain-of-thought + few-shot + strict rules) covering implicit steps,
# dependency ordering, and CSV field mapping. Needs more .format() variables
# than the current function body supplies — wired up in 2B/2D.
SYSTEM_PROMPT_TEMPLATE = """\
Tu es ARIA, un moteur de planification d'automatisation d'API (Sopra HR Software).
Tu reçois une liste d'endpoints candidats récupérés par recherche sémantique \
et tu dois construire un plan d'exécution structuré, ordonné et complet.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENDPOINTS CANDIDATS (source : RAG pgvector)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rag_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCTION UTILISATEUR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{instruction}

CONTEXTE DÉTECTÉ PAR L'INTENT ANALYZER :
  Action   : {action}
  Entités  : {entities}
  Volume   : {quantity}
  Source   : {data_source}
  Colonnes : {csv_columns}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAISONNEMENT ATTENDU (chain-of-thought interne)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Avant de produire le JSON, raisonne mentalement dans cet ordre :

1. FILTRE   — Quels endpoints sont réellement liés à l'instruction ?
              Élimine ceux dont le business_domain ou business_action
              ne correspondent pas, même si le score RAG est élevé.

2. COMPLÈTE — Y a-t-il des étapes implicites nécessaires ?
              Exemples de chaînes naturelles :
              • Créer employé → assigner contrat → configurer congés → notifier RH
              • Créer utilisateur → assigner rôle → envoyer email d'activation
              N'invente AUCUN endpoint absent de la liste candidats.
              Si une étape implicite manque → note-la dans missing_endpoints.

3. ORDONNE  — Quelle est la dépendance logique entre étapes ?
              Une étape qui produit un ID dont une autre a besoin
              doit être exécutée en premier.
              Traduis ces relations dans depends_on.

4. MAPPE    — Si csv_columns est non vide, pour chaque étape,
              fais correspondre chaque colonne CSV à un paramètre API
              visible dans le champ Details de l'endpoint.
              Si la correspondance est incertaine → valeur null (jamais inventée).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES STRICTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Utilise UNIQUEMENT les canonical_key présents dans les endpoints candidats
✅ Un plan vide (selected_canonical_keys: []) est un résultat valide
✅ required=true  → étape bloquante (la ressource principale ne peut pas être créée sans elle)
✅ required=false → étape optionnelle (notification, audit, log)
✅ loop="csv_rows" uniquement si data_source=csv ou data_source=excel ET l'étape se répète par ligne
✅ confidence = ta propre estimation de la qualité du plan (0.0 à 1.0)
❌ N'invente aucun endpoint, paramètre, ou mapping non visible dans les candidats
❌ Aucun texte avant ou après le JSON
❌ Aucun bloc markdown (pas de ```json)
✅ field_mapping — deux usages distincts, ne les confonds pas :
   1. Correspondance directe colonne→paramètre (uniquement si data_source
      est "csv" ou "excel") : {{"colonne_csv": "nom_parametre_api"}}.
      Si data_source n'est PAS csv/excel, n'utilise JAMAIS cette forme.
   2. Règle conditionnelle PAR LIGNE, portée par l'INSTRUCTION elle-même
      (utilisable quelle que soit data_source, y compris sans CSV) :
      quand l'instruction dit explicitement "fais X pour celles qui sont Y,
      sinon Z" (ex: "approuve automatiquement celles de type congé, laisse
      les autres en attente"), et qu'une étape PATCH/PUT a besoin de cette
      valeur, code-la comme :
      {{"<colonne_source>": {{"maps_to": "<param_api_cible>",
                             "when_equals": "<valeur_qui_declenche_then>",
                             "then": "<valeur_si_egal>",
                             "else": "<valeur_sinon>"}}}}
      <colonne_source> est le nom du champ tel qu'il apparaît dans les
      données de ligne (ex: "type"). N'invente PAS de règle non présente
      dans l'instruction — si aucune condition n'est explicitement énoncée
      pour un paramètre requis, laisse-le simplement absent de field_mapping
      (ne mets JAMAIS une valeur par défaut de ton cru).
❌ N'utilise field_mapping (les deux formes) que pour un besoin explicitement
   déductible de l'instruction ou de data_source — jamais par supposition.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXEMPLE 1 — Création en masse depuis CSV

ENDPOINTS CANDIDATS :
Endpoint #1
Method: POST
Path: /employees
Canonical key: POST /employees
Business domain: employee
Business action: create
Score: 0.9312
Details: Creates a new employee. Body params: first_name, last_name, email, hire_date.

---

Endpoint #2
Method: POST
Path: /employees/{{id}}/contract
Canonical key: POST /employees/{{id}}/contract
Business domain: employee
Business action: assign_contract
Score: 0.8104
Details: Assigns a contract to an existing employee. Path param: id. Body params: contract_type, start_date.

---

Endpoint #3
Method: POST
Path: /employees/{{id}}/leaves
Canonical key: POST /employees/{{id}}/leaves
Business domain: leave
Business action: configure
Score: 0.7450
Details: Configures leave entitlements for an employee. Path param: id. Body params: leave_type, days_entitled.

---

Endpoint #4
Method: POST
Path: /notifications/send
Canonical key: POST /notifications/send
Business domain: notification
Business action: send
Score: 0.6201
Details: Sends an email notification. Body params: recipient_email, template_id, payload.

INSTRUCTION : "Crée 200 employés depuis ce CSV"
CONTEXTE : action=bulk_create, entités=[employee], volume=200, source=csv, colonnes=[prénom, nom, email, type_contrat, date_debut]

RÉPONSE ATTENDUE :
{{
  "selected_canonical_keys": [
    "POST /employees",
    "POST /employees/{{id}}/contract",
    "POST /employees/{{id}}/leaves",
    "POST /notifications/send"
  ],
  "steps": [
    {{
      "order": 1,
      "canonical_key": "POST /employees",
      "action": "Créer l'employé",
      "required": true,
      "depends_on": [],
      "loop": "csv_rows",
      "field_mapping": {{
        "prénom": "first_name",
        "nom": "last_name",
        "email": "email",
        "date_debut": "hire_date",
        "type_contrat": null
      }}
    }},
    {{
      "order": 2,
      "canonical_key": "POST /employees/{{id}}/contract",
      "action": "Assigner le contrat à l'employé",
      "required": true,
      "depends_on": [1],
      "loop": "csv_rows",
      "field_mapping": {{
        "type_contrat": "contract_type",
        "date_debut": "start_date",
        "prénom": null,
        "nom": null,
        "email": null
      }}
    }},
    {{
      "order": 3,
      "canonical_key": "POST /employees/{{id}}/leaves",
      "action": "Configurer les congés de l'employé",
      "required": true,
      "depends_on": [1],
      "loop": "csv_rows",
      "field_mapping": {{}}
    }},
    {{
      "order": 4,
      "canonical_key": "POST /notifications/send",
      "action": "Notifier le service RH",
      "required": false,
      "depends_on": [1, 2, 3],
      "loop": null,
      "field_mapping": {{
        "email": "recipient_email"
      }}
    }}
  ],
  "reasoning": "L'instruction demande une création en masse d'employés. POST /employees est l'étape principale (boucle sur chaque ligne CSV). Le contrat et les congés sont des étapes implicites nécessaires à l'onboarding complet, dépendantes de l'ID créé à l'étape 1. La notification RH est optionnelle et se déclenche une seule fois après toutes les créations.",
  "missing_endpoints": [],
  "confidence": 0.91
}}

---

## EXEMPLE 2 — Instruction vague, endpoints non correspondants

ENDPOINTS CANDIDATS :
Endpoint #1
Method: GET
Path: /payroll/reports
Canonical key: GET /payroll/reports
Business domain: payroll
Business action: report
Score: 0.5102
Details: Returns payroll summary reports. Query params: month, year, department_id.

INSTRUCTION : "Envoie un message à tous les employés"
CONTEXTE : action=send, entités=[employee], volume=null, source=null, colonnes=[]

RÉPONSE ATTENDUE :
{{
  "selected_canonical_keys": [],
  "steps": [],
  "reasoning": "Aucun endpoint candidat ne correspond à une action d'envoi de message ou notification. GET /payroll/reports concerne les rapports de paie, pas la messagerie.",
  "missing_endpoints": ["POST /messages ou POST /notifications/send — endpoint d'envoi de message absent de la liste candidats"],
  "confidence": 0.0
}}

---

## EXEMPLE 3 — Mise à jour unique, pas de CSV

ENDPOINTS CANDIDATS :
Endpoint #1
Method: PUT
Path: /employees/{{id}}/salary
Canonical key: PUT /employees/{{id}}/salary
Business domain: employee
Business action: update_salary
Score: 0.9501
Details: Updates the salary of an existing employee. Path param: id. Body params: amount, currency, effective_date.

---

Endpoint #2
Method: POST
Path: /employees/{{id}}/leaves
Canonical key: POST /employees/{{id}}/leaves
Business domain: leave
Business action: configure
Score: 0.5210
Details: Configures leave entitlements. Path param: id. Body params: leave_type, days_entitled.

INSTRUCTION : "Mettre à jour le salaire de l'employé 42 à 75000 EUR"
CONTEXTE : action=update, entités=[employee, salary], volume=1, source=null, colonnes=[]

RÉPONSE ATTENDUE :
{{
  "selected_canonical_keys": [
    "PUT /employees/{{id}}/salary"
  ],
  "steps": [
    {{
      "order": 1,
      "canonical_key": "PUT /employees/{{id}}/salary",
      "action": "Mettre à jour le salaire de l'employé",
      "required": true,
      "depends_on": [],
      "loop": null,
      "field_mapping": {{}}
    }}
  ],
  "reasoning": "L'instruction cible un seul employé (ID 42) pour une mise à jour de salaire. PUT /employees/{{id}}/salary correspond exactement. POST /employees/{{id}}/leaves est hors scope (congés, pas salaire) — éliminé malgré sa présence dans les candidats.",
  "missing_endpoints": [],
  "confidence": 0.97
}}

---

## EXEMPLE 4 — Création multi-lignes + règle conditionnelle par ligne (pas de CSV)

ENDPOINTS CANDIDATS :
Endpoint #1
Method: POST
Path: /api/requests
Canonical key: POST /api/requests
Business domain: human_resources
Business action: create_time_off_request
Score: 0.9180
Details: Creates an absence request. Body params: nom_employe, type, date_debut, date_fin, motif.

---

Endpoint #2
Method: PATCH
Path: /api/requests/{{request_id}}
Canonical key: PATCH /api/requests/{{request_id}}
Business domain: human_resources
Business action: update_request_status
Score: 0.8340
Details: Updates the status of an absence request. Path param: request_id. Body param: statut.

INSTRUCTION : "Créer 5 demandes d'absence pour les employés suivants, puis approuve automatiquement celles de type \"congé\" et laisse les autres en attente : ..."
CONTEXTE : action=bulk_create, entités=[absence_request], volume=5, source=non précisé, colonnes=aucune

RÉPONSE ATTENDUE :
{{
  "selected_canonical_keys": [
    "POST /api/requests",
    "PATCH /api/requests/{{request_id}}"
  ],
  "steps": [
    {{
      "order": 1,
      "canonical_key": "POST /api/requests",
      "action": "Créer la demande d'absence",
      "required": true,
      "depends_on": [],
      "loop": null,
      "field_mapping": {{}}
    }},
    {{
      "order": 2,
      "canonical_key": "PATCH /api/requests/{{request_id}}",
      "action": "Approuver automatiquement si type=congé, sinon laisser en attente",
      "required": true,
      "depends_on": [1],
      "loop": null,
      "field_mapping": {{
        "type": {{"maps_to": "statut", "when_equals": "congé", "then": "approuvée", "else": "en attente"}}
      }}
    }}
  ],
  "reasoning": "L'instruction énonce explicitement une règle conditionnelle sur le champ 'type' pour décider du statut à appliquer — codée en field_mapping sur l'étape 2 plutôt que laissée à une valeur par défaut, pour que l'exécution reflète réellement la règle demandée au lieu de réécrire le statut déjà posé par la création.",
  "missing_endpoints": [],
  "confidence": 0.9
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAINTENANT, PRODUIS LE JSON POUR L'INSTRUCTION CI-DESSUS.
Aucun texte avant ou après. JSON valide uniquement.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

# ARIA-WORKFLOW-V2: exact marker text from SYSTEM_PROMPT_TEMPLATE's closing
# section — used to splice the existing_workflow block in right before it
# (see generate_plan_selection). Must match verbatim or the splice silently
# no-ops (str.replace finds nothing, prompt is sent without the block).
_MAINTENANT_MARKER = (
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "MAINTENANT, PRODUIS LE JSON POUR L'INSTRUCTION CI-DESSUS."
)

# ARIA-RAG-FIX: message affiché à la place d'un rag_context vide, plutôt
# qu'une chaîne vide silencieuse dans plan.metadata.
FALLBACK_MESSAGE = (
    "Aucun endpoint pertinent trouvé. Demande à l'utilisateur de préciser son instruction."
)

# ARIA-WORKFLOW-V2: replaces the minimal (keys + reasoning) schema with the
# full structured plan — steps with order/required/depends_on/loop/
# field_mapping, plus missing_endpoints and confidence. Not yet consumed by
# generate_plan_selection()'s body (still returns just the key list) — wired
# up in 2D.
_PLAN_SELECTION_SCHEMA = {
    "name": "plan_selection",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "selected_canonical_keys": {
                "type": "array",
                "items": {"type": "string"}
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "order":         {"type": "integer"},
                        "canonical_key": {"type": "string"},
                        "action":        {"type": "string"},
                        "required":      {"type": "boolean"},
                        "depends_on":    {"type": "array", "items": {"type": "integer"}},
                        "loop":          {"type": ["string", "null"]},
                        "field_mapping": {"type": "object"},
                    },
                    "required": [
                        "order", "canonical_key", "action",
                        "required", "depends_on", "loop", "field_mapping"
                    ],
                    "additionalProperties": False,
                },
            },
            "reasoning":         {"type": "string"},
            "missing_endpoints": {"type": "array", "items": {"type": "string"}},
            "confidence":        {"type": "number"},
        },
        "required": [
            "selected_canonical_keys", "steps",
            "reasoning", "missing_endpoints", "confidence"
        ],
        "additionalProperties": False,
    },
}


def generate_plan_selection(
    instruction: str,
    rag_context: str,
    client,
    intent: "BusinessIntent | None" = None,
    existing_workflow: "WorkflowModel | None" = None,
    csv_columns: List[str] | None = None,
) -> Optional[Dict]:
    """
    Demande au LLM quels endpoints candidats (rag_context, déjà récupérés par
    RAG) appartiennent réellement au plan pour cette instruction, dans quel
    ordre, avec quelles étapes implicites et quel mapping CSV.

    Retour :
    - None -> aucune décision prise (rag_context vide, ou l'appel LLM a
              échoué) — l'appelant doit revenir au comportement précédent
              (utiliser tous les candidats RAG sans filtrage).
    - dict -> décision explicite du LLM : selected_canonical_keys, steps,
              reasoning, missing_endpoints, confidence. selected_canonical_keys
              peut être vide — à respecter tel quel, un plan à 0 étape est un
              résultat valide, pas un échec.

    plan_builder.py NE DOIT PAS faire confiance aveuglément aux clés
    retournées : il doit les filtrer contre l'ensemble réellement retourné
    par la recherche RAG avant de construire les PlanStep.
    """
    if not rag_context or not rag_context.strip():
        return None

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        rag_context=rag_context,
        instruction=instruction,
        action=intent.action if intent else "non précisé",
        entities=", ".join(intent.entities) if intent and intent.entities else "non précisé",
        quantity=str(intent.quantity) if intent and intent.quantity else "non précisé",
        # ARIA-WORKFLOW-V2: BusinessIntent (app/planner/models.py) has no
        # data_source/csv_columns fields. csv_columns is this function's own
        # parameter (added in 2B); data_source has no dedicated field at all,
        # so it's inferred from csv_columns being provided or not.
        data_source="csv" if csv_columns else "non précisé",
        csv_columns=", ".join(csv_columns) if csv_columns else "aucune",
    )

    if existing_workflow is not None:
        # ARIA-WORKFLOW-V2: existing_workflow.metadata_json isn't guaranteed
        # to contain a "steps" key — nothing currently writes one there
        # (checked app/workflows/*). Falls back to "non disponible" until a
        # real lookup (Phase 4) also decides how to populate this properly.
        workflow_block = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "WORKFLOW MÉTIER CONNU (appris du trafic HAR réel — priorité sur le RAG)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Nom : {existing_workflow.name}\n"
            f"Domaine : {existing_workflow.business_domain}\n"
            f"Confiance : {existing_workflow.confidence}\n"
            f"Étapes connues : {existing_workflow.metadata_json.get('steps', 'non disponible')}\n"
            "\n"
            "Utilise ces étapes comme référence d'ordre et de complétude.\n"
            "Si un endpoint de ce workflow est absent des candidats RAG,\n"
            "note-le dans missing_endpoints.\n"
        )
        prompt = prompt.replace(
            _MAINTENANT_MARKER, workflow_block + "\n" + _MAINTENANT_MARKER, 1
        )

    try:
        result = client.structured_chat(
            system_prompt=prompt,
            user_payload={"instruction": instruction},
            json_schema=_PLAN_SELECTION_SCHEMA,
            task_name="plan_generation",
        )
    except Exception as exc:
        logger.warning(
            "plan_generation.failed error=%s — falling back to unfiltered RAG results", exc,
        )
        return None

    # ARIA-WORKFLOW-V2: return the full structured dict (steps, reasoning,
    # missing_endpoints, confidence) instead of just the key list — callers
    # updated in 2E to consume it accordingly.
    return result
