import pytest
from server.anonymizer import (
    Anonymizer,
    _DEFAULT_PRESIDIO_ENTITIES,
    _is_presidio_false_positive,
)
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


# ---------------------------------------------------------------------------
# Pass 2 entity filter (presidio_entities knob) — F5
# ---------------------------------------------------------------------------

def test_default_entities_exclude_date_time():
    assert "DATE_TIME" not in _DEFAULT_PRESIDIO_ENTITIES
    assert "PERSON" in _DEFAULT_PRESIDIO_ENTITIES
    assert "EMAIL_ADDRESS" in _DEFAULT_PRESIDIO_ENTITIES


def test_default_anonymizer_does_not_act_on_date_time():
    anon = Anonymizer(registry=_make_registry({}), presidio_enabled=True)
    assert "DATE_TIME" not in anon._presidio_entities
    assert "ORGANIZATION" in anon._presidio_entities


def test_explicit_entity_list_is_honoured_verbatim():
    anon = Anonymizer(registry=_make_registry({}), presidio_enabled=True,
                      presidio_entities=["PERSON"])
    assert anon._presidio_entities == frozenset({"PERSON"})


# ---------------------------------------------------------------------------
# Pass 2 skip-rules for non-PII detections — F5 / F4
# ---------------------------------------------------------------------------

def test_skip_guid_and_hex_id():
    assert _is_presidio_false_positive(
        "550e8400-e29b-41d4-a716-446655440000", "ORGANIZATION")
    assert _is_presidio_false_positive("ba67bb89", "ORGANIZATION")


def test_skip_pure_number_and_iso_date_for_name_entities():
    assert _is_presidio_false_positive("218", "ORGANIZATION")
    assert _is_presidio_false_positive("2026-01-21", "ORGANIZATION")
    assert _is_presidio_false_positive("2026-01-21T10:30:00", "PERSON")


def test_numeric_pii_entities_are_not_skipped_when_numeric():
    # A phone number / card is numeric but IS PII: must stay masked.
    assert not _is_presidio_false_positive("0612345678", "PHONE_NUMBER")
    assert not _is_presidio_false_positive("4111111111111111", "CREDIT_CARD")


def test_skip_dax_and_schema_keywords():
    for kw in ("DIVIDE", "Hours", "Ratio", "COUNTX", "SUMMARIZECOLUMNS"):
        assert _is_presidio_false_positive(kw, "ORGANIZATION"), kw


def test_skip_priority_tier_prefix_pattern():
    for label in ("P1-Kritisch", "P2-Hoog", "P3-Medium", "P4-Laag"):
        assert _is_presidio_false_positive(label, "ORGANIZATION"), label


def test_real_pii_is_not_a_false_positive():
    assert not _is_presidio_false_positive("John Smith", "PERSON")
    assert not _is_presidio_false_positive("Wu-Jackson Holding", "ORGANIZATION")
    assert not _is_presidio_false_positive("Project Phoenix", "ORGANIZATION")


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_leaves_dates_and_guids_but_masks_person():
    anon = Anonymizer(registry=_make_registry({}), presidio_enabled=True)
    result = anon.anonymize_text(
        "John Smith opened ticket 550e8400-e29b-41d4-a716-446655440000 "
        "on 2026-01-15 using DIVIDE in a measure")
    assert "550e8400-e29b-41d4-a716-446655440000" in result  # GUID untouched
    assert "2026-01-15" in result                             # date untouched
    assert "DIVIDE" in result                                 # DAX keyword untouched
    assert "John Smith" not in result                         # real PII masked
