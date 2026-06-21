import re


UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)

NUMERIC_ID_PATTERN = re.compile(r"^\d+$")

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

# Matches prefix_word_digits style IDs used by many internal systems.
# e.g. emp_soph_001, ctr_soph_001, pay_soph_001, badge_soph_001, pos_swe_senior_01
# Pattern: letters_letters..._digits  (underscore separator, ends with numeric suffix)
PREFIXED_RESOURCE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+_\d+$",
    re.IGNORECASE,
)
