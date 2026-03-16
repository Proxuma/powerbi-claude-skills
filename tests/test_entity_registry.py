import pytest
from server.entity_registry import EntityRegistry, _normalize, _default_alias


def test_registry_builds_mapping_from_dax_results():
    mock_response = {"results": [{"tables": [{"rows": [
        {"[Company Name]": "Acme Corp"},
        {"[Company Name]": "Beta Inc"},
    ]}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Company Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    assert registry.anonymize("Acme Corp") == "Client_A"
    assert registry.anonymize("Beta Inc") == "Client_B"
    assert registry.deanonymize("Client_A") == "Acme Corp"
    assert registry.deanonymize("Client_B") == "Beta Inc"


def test_registry_is_case_insensitive():
    mock_response = {"results": [{"tables": [{"rows": [
        {"[Company Name]": "Acme Corp"},
    ]}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Company Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    assert registry.anonymize("acme corp") == "Client_A"
    assert registry.anonymize("ACME CORP") == "Client_A"


def test_registry_longest_match_first():
    mock_response = {"results": [{"tables": [{"rows": [
        {"[Company Name]": "Acme Corp"},
        {"[Company Name]": "Acme Corp BV"},
    ]}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Company Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    text = "Invoice for Acme Corp BV was sent"
    result = registry.anonymize_text(text)
    assert "Acme Corp BV" not in result
    assert "Client_" in result


def test_registry_handles_empty_results():
    mock_response = {"results": [{"tables": [{"rows": []}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Company Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    assert registry.anonymize("Unknown Corp") == "Unknown Corp"
    assert len(registry.get_mapping()) == 0


def test_registry_handles_dax_failure_gracefully():
    def failing_executor(q):
        raise Exception("API timeout")

    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Company Name]"]},
        dax_executor=failing_executor,
    )
    registry.initialize()
    assert registry.is_degraded is True
    assert len(registry.get_mapping()) == 0


def test_registry_multiple_categories():
    def mock_executor(query):
        if "Companies" in query:
            return {"results": [{"tables": [{"rows": [
                {"[Company Name]": "Acme Corp"},
            ]}]}]}
        elif "Resources" in query:
            return {"results": [{"tables": [{"rows": [
                {"[Full Name]": "Jan de Vries"},
            ]}]}]}
        return {"results": [{"tables": [{"rows": []}]}]}

    registry = EntityRegistry(
        sensitive_columns={
            "client": ["'Companies'[Company Name]"],
            "resource": ["'Resources'[Full Name]"],
        },
        dax_executor=mock_executor,
    )
    registry.initialize()
    assert registry.anonymize("Acme Corp") == "Client_A"
    assert registry.anonymize("Jan de Vries") == "Resource_1"


def test_normalize_strips_and_lowercases():
    assert _normalize("  Hello World  ") == "hello world"
    assert _normalize("UPPER") == "upper"


def test_default_alias_unknown_category():
    assert _default_alias("project", 0) == "Project_1"
    assert _default_alias("project", 2) == "Project_3"


def test_default_alias_client_overflow():
    # After 26 clients, switches from letters to numbers
    assert _default_alias("client", 0) == "Client_A"
    assert _default_alias("client", 25) == "Client_Z"
    assert _default_alias("client", 26) == "Client_27"


def test_deanonymize_unknown_alias_returns_original():
    registry = EntityRegistry(
        sensitive_columns={},
        dax_executor=lambda q: {},
    )
    registry.initialize()
    assert registry.deanonymize("Unknown_Alias") == "Unknown_Alias"


def test_anonymize_text_with_no_entities():
    registry = EntityRegistry(
        sensitive_columns={},
        dax_executor=lambda q: {},
    )
    registry.initialize()
    assert registry.anonymize_text("Hello world") == "Hello world"
    assert registry.anonymize_text("") == ""
    assert registry.anonymize_text(None) is None


def test_get_warnings_after_partial_failure():
    call_count = 0

    def mixed_executor(query):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"results": [{"tables": [{"rows": [
                {"[Name]": "Good Corp"},
            ]}]}]}
        raise Exception("Connection lost")

    registry = EntityRegistry(
        sensitive_columns={"client": ["'T1'[Name]", "'T2'[Name]"]},
        dax_executor=mixed_executor,
    )
    registry.initialize()
    assert registry.is_degraded is True
    assert registry.anonymize("Good Corp") == "Client_A"
    assert len(registry.get_warnings()) == 1
    assert "Connection lost" in registry.get_warnings()[0]


def test_anonymize_text_case_insensitive_replacement():
    mock_response = {"results": [{"tables": [{"rows": [
        {"[Name]": "Acme Corp"},
    ]}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'T'[Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    result = registry.anonymize_text("Sent to ACME CORP today")
    assert "ACME CORP" not in result
    assert "Client_A" in result


def test_duplicate_values_across_columns_not_duplicated():
    mock_response = {"results": [{"tables": [{"rows": [
        {"[Name]": "Acme Corp"},
    ]}]}]}
    registry = EntityRegistry(
        sensitive_columns={"client": ["'T1'[Name]", "'T2'[Name]"]},
        dax_executor=lambda q: mock_response,
    )
    registry.initialize()
    # Same value from two columns should only get one alias
    assert len(registry.get_mapping()) == 1
    assert registry.anonymize("Acme Corp") == "Client_A"
