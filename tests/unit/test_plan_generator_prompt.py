"""FIX 2 (post-Phase 8 finding) — SYSTEM_PROMPT_TEMPLATE's RÈGLES STRICTES
section must instruct the LLM to zero out field_mapping when no CSV/Excel
source is provided. tc_006/tc_007 in evaluation/golden_dataset.json found
the LLM populating field_mapping for non-bulk, non-CSV instructions.
"""
from app.planner.plan_generator import SYSTEM_PROMPT_TEMPLATE


def _render(**overrides):
    defaults = dict(
        rag_context="ctx", instruction="instr", action="create",
        entities="employee", quantity="1", data_source="non précisé",
        csv_columns="aucune",
    )
    defaults.update(overrides)
    return SYSTEM_PROMPT_TEMPLATE.format(**defaults)


class TestFieldMappingRule:
    def test_rule_text_present(self):
        rendered = _render()
        assert 'field_mapping doit être {}' in rendered
        assert "csv" in rendered.lower() and "excel" in rendered.lower()

    def test_renders_without_crashing_for_csv_source(self):
        # Regression check: {{}} in the new rule must stay literal after
        # .format() even when other placeholders (csv_columns) are filled.
        rendered = _render(data_source="csv", csv_columns="prénom, nom, email")
        assert 'field_mapping doit être {}' in rendered
        assert "prénom, nom, email" in rendered

    def test_no_stray_double_braces_in_new_rule(self):
        rendered = _render()
        rule_start = rendered.index("Si data_source n'est PAS")
        rule_end = rule_start + 250
        snippet = rendered[rule_start:rule_end]
        assert "{{" not in snippet and "}}" not in snippet
