"""Tests for reverse-mapping alias literals in inbound DAX queries.

The AI only ever sees aliases, so filters it writes on aliased name strings
(e.g. 'Companies'[company_name] = "Client_A") would silently return 0 rows
against the real tenant. rewrite_alias_literals rewrites known aliases back
to real values, but only inside double-quoted string literals.
"""

from server.anonymizer import Anonymizer, rewrite_alias_literals
from server.entity_registry import EntityRegistry


MAPPING = {
    "Client_A": "Acme & Zonen BV",
    "Client_B": "Globex Corporation",
    "Resource_1": "Jan de Vries",
    "Workspace_1": "Proxuma Demo",
    "Dataset_1": "Proxuma - Data model - Template",
    "<PERSON_1>": "Piet Janssen",
}


def _make_registry(mapping: dict[str, str]) -> EntityRegistry:
    """Helper: build a registry with pre-loaded mapping (alias -> real)."""
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    for alias, real_val in mapping.items():
        norm = real_val.strip().lower()
        registry._forward[norm] = alias
        registry._reverse[alias] = real_val
    registry._sorted_entities = sorted(
        [(n, registry._reverse[a]) for n, a in registry._forward.items()],
        key=lambda x: len(x[1]),
        reverse=True,
    )
    return registry


def test_alias_inside_quoted_literal_is_rewritten():
    dax = "EVALUATE FILTER('Companies', 'Companies'[company_name] = \"Client_A\")"
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert result == "EVALUATE FILTER('Companies', 'Companies'[company_name] = \"Acme & Zonen BV\")"
    assert count == 1


def test_bare_alias_outside_quotes_is_not_rewritten():
    # Alias-looking text as a column alias / identifier must stay untouched.
    dax = "EVALUATE SUMMARIZECOLUMNS('T'[Client_A], 'T'[Resource_1], [Measure])"
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert result == dax
    assert count == 0


def test_unknown_alias_stays_untouched():
    dax = "EVALUATE FILTER('Companies', 'Companies'[company_name] = \"Client_ZZZ\")"
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert result == dax
    assert count == 0


def test_presidio_token_is_rewritten():
    dax = "EVALUATE FILTER('Contacts', 'Contacts'[contact_name] = \"<PERSON_1>\")"
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert result == "EVALUATE FILTER('Contacts', 'Contacts'[contact_name] = \"Piet Janssen\")"
    assert count == 1


def test_multiple_aliases_in_one_query():
    dax = (
        'EVALUATE FILTER(\'Tickets\', '
        '\'Tickets\'[company_name] IN {"Client_A", "Client_B"} '
        '&& \'Tickets\'[resource_name] = "Resource_1")'
    )
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert '"Acme & Zonen BV"' in result
    assert '"Globex Corporation"' in result
    assert '"Jan de Vries"' in result
    assert "Client_A" not in result
    assert count == 3


def test_workspace_and_dataset_aliases_are_rewritten():
    dax = 'EVALUATE FILTER(\'Items\', \'Items\'[workspace] = "Workspace_1" && \'Items\'[dataset] = "Dataset_1")'
    result, count = rewrite_alias_literals(dax, MAPPING)
    assert '"Proxuma Demo"' in result
    assert '"Proxuma - Data model - Template"' in result
    assert count == 2


def test_real_value_with_double_quote_is_escaped():
    mapping = {"Client_A": 'The "Best" Company'}
    dax = "EVALUATE FILTER('C', 'C'[name] = \"Client_A\")"
    result, count = rewrite_alias_literals(dax, mapping)
    assert result == "EVALUATE FILTER('C', 'C'[name] = \"The \"\"Best\"\" Company\")"
    assert count == 1


def test_anonymizer_deanonymize_dax_uses_registry_and_presidio():
    registry = _make_registry({"Client_A": "Acme & Zonen BV"})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    anon._presidio_mapping["<PERSON_1>"] = "Piet Janssen"
    dax = 'EVALUATE FILTER(\'T\', \'T\'[c] = "Client_A" || \'T\'[p] = "<PERSON_1>")'
    result, count = anon.deanonymize_dax(dax)
    assert '"Acme & Zonen BV"' in result
    assert '"Piet Janssen"' in result
    assert count == 2


def test_anonymizer_disabled_returns_query_unchanged():
    registry = _make_registry({"Client_A": "Acme & Zonen BV"})
    anon = Anonymizer(registry=registry, enabled=False)
    dax = "EVALUATE FILTER('T', 'T'[c] = \"Client_A\")"
    result, count = anon.deanonymize_dax(dax)
    assert result == dax
    assert count == 0


def test_round_trip_response_is_re_aliased():
    # After the rewrite hits the real tenant, real values coming back must be
    # re-aliased before the AI sees them (server passes responses through
    # anonymize_json).
    registry = _make_registry({"Client_A": "Acme & Zonen BV"})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    dax = "EVALUATE FILTER('C', 'C'[name] = \"Client_A\")"
    rewritten, count = anon.deanonymize_dax(dax)
    assert count == 1
    fake_response = {"results": [{"tables": [{"rows": [{"name": "Acme & Zonen BV"}]}]}]}
    anonymized = anon.anonymize_json(fake_response)
    assert anonymized["results"][0]["tables"][0]["rows"][0]["name"] == "Client_A"
