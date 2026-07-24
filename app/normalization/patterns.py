import re


UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)

NUMERIC_ID_PATTERN = re.compile(r"^\d+$")

# Clé composite deux entiers séparés par underscore (ex: 123_456).
COMPOSITE_NUMERIC_ID_PATTERN = re.compile(r"^\d+_\d+$")

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T")

JWT_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"
)

HASH_PATTERN = re.compile(r"^[a-fA-F0-9]{24,}$")

INVOICE_ID_PATTERN = re.compile(
    r"^(INV|INVOICE)-?\d{4}-?\d+$",
    re.IGNORECASE,
)

PAYMENT_ID_PATTERN = re.compile(
    r"^(PAY|PAYMENT)-?\d{4}-?\d+$",
    re.IGNORECASE,
)

EMPLOYEE_ID_PATTERN = re.compile(
    r"^(EMP|EMPLOYEE)-?\d+$",
    re.IGNORECASE,
)

ORDER_ID_PATTERN = re.compile(
    r"^(ORD|ORDER)-?\d+$",
    re.IGNORECASE,
)

CUSTOMER_ID_PATTERN = re.compile(
    r"^(CUS|CUST|CUSTOMER)-?\d+$",
    re.IGNORECASE,
)

CONTRACT_ID_PATTERN = re.compile(
    r"^(CTR|CONT|CONTRACT)-?\d+$",
    re.IGNORECASE,
)

GENERIC_BUSINESS_ID_PATTERN = re.compile(
    r"^[A-Z]{2,10}-?\d{2,}$",
    re.IGNORECASE,
)

# Code SKU / référence produit — suffixe alphanumérique MIXTE (pas purement
# numérique, sinon déjà couvert par GENERIC_BUSINESS_ID_PATTERN ci-dessus).
# Exige au moins un chiffre dans le suffixe (lookahead) pour ne jamais
# matcher une paire de mots-clés majuscules sans aucun signal numérique —
# resserré par rapport à une regex charset-only pour éviter de refaire le
# Bug 1 (mots constants confondus avec des IDs faute de signal de forme).
# ex: SKU-1234AB
SKU_CODE_PATTERN = re.compile(
    r"^[A-Z]{2,4}-(?=[A-Z0-9]{4,10}$)(?=[A-Z0-9]*\d)[A-Z0-9]+$",
    re.IGNORECASE,
)

# Slug texte + marqueur numérique isolable — contrairement à un slug texte
# pur (jamais un ID, voir dynamic_segment_detector.py), la présence d'un
# bloc de chiffres est un signal de forme fiable, indépendant de toute
# comparaison inter-requêtes.
# ex: mon-article-482 (suffixe) — nécessite 3+ segments pour ne pas
# doublonner le cas 2-segments déjà couvert par GENERIC_BUSINESS_ID_PATTERN
# (ex: "user-482" matche déjà ça).
SLUG_ID_SUFFIX_PATTERN = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)+-\d+$",
    re.IGNORECASE,
)
# ex: 482-mon-article (préfixe)
SLUG_ID_PREFIX_PATTERN = re.compile(
    r"^\d+(?:-[a-z0-9]+)+$",
)

# Matches prefix_digits and prefix_word_digits style IDs used by many
# internal systems.
# e.g. emp_301, cart_7001, ord_3001, emp_soph_001, ctr_soph_001, pos_swe_senior_01
# Pattern: letters(_letters...)*_digits  (underscore separator, ends with
# numeric suffix). The middle (?:_[a-z][a-z0-9]*)* group is now 0-or-more
# (was 1-or-more) so the 2-part form (emp_301) matches, not just 3+-part
# forms (emp_soph_001) — the 2-part form was previously invisible to every
# regex in this file (also checked EMPLOYEE_ID_PATTERN/GENERIC_BUSINESS_ID_
# PATTERN: both require a dash or nothing, never an underscore, before the
# digits) and depended entirely on dynamic_segment_detector.py's statistical
# fallback to be recognized at all.
PREFIXED_RESOURCE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)*_\d+$",
    re.IGNORECASE,
)

# Amélioration 3 : identifiants préfixés dont la partie variable est un UUID
# complet, pas juste un suffixe alphanumérique (STRIPE_ID_PATTERN l'exclut
# car son charset suffixe n'autorise pas les tirets).
# ex: usr_550e8400-e29b-41d4-a716-446655440000
PREFIXED_UUID_PATTERN = re.compile(
    r"^[a-z]{2,6}_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    re.IGNORECASE,
)

# Matches single-letter-prefixed IDs: u001, p001, o001, c042 …
# Requires exactly 1 letter + 3+ digits to avoid matching API versions (v2, v10).
SHORT_PREFIXED_ID_PATTERN = re.compile(
    r"^[a-z]\d{3,}$",
    re.IGNORECASE,
)

# Matches short hex tokens used as session/resource IDs: 9f2a, ab12cd, 3e7f9a …
# Requires 4–23 hex chars AND at least one letter (to exclude pure numeric IDs)
# and at least one digit (to exclude common English words like "face", "cafe").
SHORT_HEX_ID_PATTERN = re.compile(
    r"^(?=[a-fA-F0-9]{4,23}$)(?=.*[a-fA-F])(?=.*\d)[a-fA-F0-9]+$"
)

# ── Amélioration 1 : formats d'ID supplémentaires ─────────────────────────────

# Stripe-style IDs: ch_1AbCdEfGhIjKlMn, sub_1XyZ..., cus_9Abc…
# Pattern: 2–6 lowercase letters + underscore + 8+ alphanumeric chars.
# The long suffix distinguishes these from slug-style segments (foo_bar).
# Threshold lowered from 10 to 8 — real Stripe-style IDs as short as 8
# suffix characters (e.g. cus_A1b2C3D4) were previously missed entirely.
STRIPE_ID_PATTERN = re.compile(
    r"^[a-z]{2,6}_[A-Za-z0-9]{8,}$"
)

# ID hexadécimal préfixé "0x" (courant sur les APIs blockchain/crypto).
HEX_0X_PATTERN = re.compile(r"^0x[0-9a-fA-F]{4,}$")

# ULID — Universally Unique Lexicographically Sortable Identifier.
# 26 chars in Crockford's Base32 alphabet (0-9, A-H, J, K, M, N, P-T, V-Z).
# Excludes I, L, O, U to avoid visual ambiguity.
ULID_PATTERN = re.compile(
    r"^[0-9A-HJKMNP-TV-Z]{26}$"
)

# Segment de version d'API générique — v1, v2, v21, v2.3... En complément de
# _STATIC_SEGMENTS (parameter_detector.py) qui n'énumère que v1-v20 : une
# regex couvre aussi les versions au-delà de 20 et les versions mineures
# (v2.3), qu'une liste en dur ne peut pas anticiper.
VERSION_SEGMENT_PATTERN = re.compile(r"^v\d+(\.\d+)?$", re.IGNORECASE)
