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


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
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


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_month_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    for month in months:
        result = anon.anonymize_text(f"Tickets created in {month} 2026")
        assert month in result, f"{month} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_priority_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    priorities = ["Critical", "High", "Medium", "Low", "Kritiek", "Hoog", "Gemiddeld", "Laag"]
    for priority in priorities:
        result = anon.anonymize_text(f"Priority: {priority}")
        assert priority in result, f"{priority} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_day_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in days:
        result = anon.anonymize_text(f"Created on {day}")
        assert day in result, f"{day} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_still_catches_real_pii():
    """Ensure the allowlist doesn't break real PII detection."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    result = anon.anonymize_text("Email john.smith@company.com about the March report")
    assert "john.smith@company.com" not in result
    assert "March" in result


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_still_catches_standalone_person_name():
    """Person names without email context should still be caught.

    If this fails at threshold 0.7, lower to 0.6 and add more allowlist
    entries instead. Presidio scores person names 0.5-0.85 depending on context.
    """
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    result = anon.anonymize_text("The ticket was assigned to John Smith for resolution")
    assert "John Smith" not in result


def test_dutch_name_with_tussenvoegsel():
    """M5: Dutch compound names with tussenvoegsels are anonymized."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "Ticket assigned to Pieter van den Berg and Jan de Vries."
    result = anon.anonymize_text(text)
    assert "Pieter van den Berg" not in result
    assert "Jan de Vries" not in result


def test_dutch_name_double_barrel():
    """M5: Hyphenated Dutch names are anonymized."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "Jan-Willem de Groot handled the request."
    result = anon.anonymize_text(text)
    assert "Jan-Willem de Groot" not in result


def test_dutch_name_initial_tussenvoegsel():
    """M5: Initial + tussenvoegsel patterns are anonymized."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "P. van den Berg approved the change."
    result = anon.anonymize_text(text)
    assert "P. van den Berg" not in result


def test_dutch_months_not_anonymized():
    """M5: Dutch month names should NOT be flagged as PII."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "Ticket created in januari 2026, resolved on maandag."
    result = anon.anonymize_text(text)
    assert "januari" in result
    assert "maandag" in result


def test_dutch_name_alias_consistency():
    """M5: Same Dutch name gets same alias across calls."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text1 = "Pieter van den Berg created the ticket."
    text2 = "The ticket was resolved by Pieter van den Berg."
    result1 = anon.anonymize_text(text1)
    result2 = anon.anonymize_text(text2)
    # Extract the alias used in result1
    alias = result1.split(" created")[0]
    assert alias in result2


def test_financial_pass_off_by_default():
    """S6: Financial anonymization is disabled by default."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    text = "Revenue was €125,000.00 this quarter."
    result = anon.anonymize_text(text)
    assert "€125,000.00" in result


def test_financial_pass_when_enabled():
    """S6: When enabled, currency amounts are noised."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False, anonymize_financials=True, financial_noise_pct=10)
    text = "Revenue was €125,000.00 this quarter."
    result = anon.anonymize_text(text)
    assert "€125,000.00" not in result
    assert "€" in result


def test_financial_pass_deterministic_same_session():
    """S6: Same value in same session produces same noised output."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False, anonymize_financials=True, financial_noise_pct=10)
    text1 = "Cost: €50,000"
    text2 = "Total cost: €50,000"
    result1 = anon.anonymize_text(text1)
    result2 = anon.anonymize_text(text2)
    import re
    amounts1 = re.findall(r"€[\d.,]+", result1)
    amounts2 = re.findall(r"€[\d.,]+", result2)
    assert amounts1[0] == amounts2[0]


def test_financial_pass_dollar_amounts():
    """S6: Dollar amounts are also noised when enabled."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=False, anonymize_financials=True, financial_noise_pct=10)
    text = "Billed $2,500.00 to the client."
    result = anon.anonymize_text(text)
    assert "$2,500.00" not in result
