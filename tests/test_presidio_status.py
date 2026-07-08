"""Tests for the Presidio availability check and Pass 2 status reporting."""
from server.anonymizer import Anonymizer, PRESIDIO_INSTALL_HINT
from server.entity_registry import EntityRegistry


def _make_anonymizer(presidio_enabled: bool = True, enabled: bool = True) -> Anonymizer:
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    return Anonymizer(registry=registry, presidio_enabled=presidio_enabled, enabled=enabled)


def test_status_inactive_when_presidio_not_installed():
    """Config says Pass 2 on, packages missing: status must say INACTIVE with install hint."""
    anon = _make_anonymizer(presidio_enabled=True)
    anon._presidio_available = False  # simulate missing packages
    assert anon.presidio_state() == "not_installed"
    line = anon.presidio_status_line()
    assert "Pass 2 (Presidio): INACTIVE" in line
    assert "pip install presidio-analyzer presidio-anonymizer spacy" in line
    assert "python -m spacy download en_core_web_sm" in line


def test_status_active_when_presidio_available():
    anon = _make_anonymizer(presidio_enabled=True)
    anon._presidio_available = True  # simulate installed packages
    assert anon.presidio_state() == "active"
    assert anon.presidio_status_line() == "Pass 2 (Presidio): ACTIVE"


def test_status_inactive_when_disabled_in_config():
    """presidio_enabled false in config: INACTIVE regardless of installed packages."""
    anon = _make_anonymizer(presidio_enabled=False)
    anon._presidio_available = True
    assert anon.presidio_state() == "disabled"
    line = anon.presidio_status_line()
    assert "Pass 2 (Presidio): INACTIVE" in line
    assert "disabled in config" in line


def test_status_inactive_when_anonymization_disabled():
    anon = _make_anonymizer(presidio_enabled=True, enabled=False)
    assert anon.presidio_state() == "disabled"
    assert "INACTIVE" in anon.presidio_status_line()


def test_status_failed_when_runtime_error_recorded():
    """A working install that fails at runtime (e.g. missing spaCy model) shows the error."""
    anon = _make_anonymizer(presidio_enabled=True)
    anon._presidio_available = True
    anon._presidio_error = "Can't find model 'en_core_web_sm'"
    assert anon.presidio_state() == "failed"
    line = anon.presidio_status_line()
    assert "INACTIVE" in line
    assert "en_core_web_sm" in line


def test_anonymize_text_skips_pass2_when_unavailable():
    """Pass 2 must be skipped cleanly (no import attempt) when packages are missing."""
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    registry.register_dynamic("Contoso", "client", 0)
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    anon._presidio_available = False
    result = anon.anonymize_text("Ticket for Contoso about John Smith")
    assert "Contoso" not in result  # Pass 1 still works
    assert "John Smith" in result   # Pass 2 did not run, and did not crash


def test_availability_check_is_cached():
    anon = _make_anonymizer(presidio_enabled=True)
    first = anon.presidio_available
    assert anon._presidio_available is first  # cached after first check
    assert anon.presidio_available is first


def test_install_hint_names_all_packages():
    for pkg in ("presidio-analyzer", "presidio-anonymizer", "spacy", "en_core_web_sm"):
        assert pkg in PRESIDIO_INSTALL_HINT
