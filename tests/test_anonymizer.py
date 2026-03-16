import pytest
from server.anonymizer import Anonymizer
from server.entity_registry import EntityRegistry

try:
    from presidio_analyzer import AnalyzerEngine
    HAS_PRESIDIO = True
except ImportError:
    HAS_PRESIDIO = False


def _make_registry(mapping: dict[str, str]) -> EntityRegistry:
    """Helper: build a registry with pre-loaded mapping."""
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    for real_val, alias in mapping.items():
        norm = real_val.strip().lower()
        registry._forward[norm] = alias
        registry._reverse[alias] = real_val
    registry._sorted_entities = sorted(
        [(n, registry._reverse[a]) for n, a in registry._forward.items()],
        key=lambda x: len(x[1]),
        reverse=True,
    )
    return registry


def test_anonymizer_replaces_known_entities():
    registry = _make_registry({"Acme Corp": "Client_A", "Jan de Vries": "Resource_1"})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "Acme Corp ticket assigned to Jan de Vries"
    result = anon.anonymize_text(text)
    assert "Acme Corp" not in result
    assert "Jan de Vries" not in result
    assert "Client_A" in result
    assert "Resource_1" in result


def test_anonymizer_json_deep_replaces():
    registry = _make_registry({"Acme Corp": "Client_A"})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    data = {"results": [{"tables": [{"rows": [
        {"name": "Acme Corp", "value": 42}
    ]}]}]}
    result = anon.anonymize_json(data)
    assert result["results"][0]["tables"][0]["rows"][0]["name"] == "Client_A"
    assert result["results"][0]["tables"][0]["rows"][0]["value"] == 42


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_anonymizer_presidio_catches_unknown_pii():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    text = "Call John Smith at john@example.com"
    result = anon.anonymize_text(text)
    assert "john@example.com" not in result


def test_anonymizer_does_not_double_replace():
    registry = _make_registry({"Jan de Vries": "Resource_1"})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    text = "Assigned to Jan de Vries"
    result = anon.anonymize_text(text)
    assert result.count("Resource_1") == 1
    assert "PERSON" not in result


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_anonymizer_tracks_presidio_detections():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    anon.anonymize_text("Email sarah@company.com for details")
    mapping = anon.get_full_mapping()
    presidio_keys = [k for k in mapping if k.startswith("<")]
    assert len(presidio_keys) >= 1


def test_anonymizer_disabled():
    registry = _make_registry({"Acme Corp": "Client_A"})
    anon = Anonymizer(registry=registry, presidio_enabled=False, enabled=False)
    text = "Acme Corp data"
    result = anon.anonymize_text(text)
    assert result == text
