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
        fail_on_degraded=False,  # degrading is now opt-in; this test covers that path
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
        fail_on_degraded=False,  # degrading is now opt-in; this test covers that path
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


def _registry_with(values):
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    for value in values:
        registry.register_dynamic(value, "client")
    return registry


def test_short_client_name_does_not_corrupt_words():
    """A client named "IT" must not rewrite those letters inside other words."""
    registry = _registry_with(["IT"])
    result = registry.anonymize_text("quality items in the IT backlog")
    assert result == "quality items in the Client_A backlog"


def test_month_like_client_name_does_not_corrupt_words():
    """A client named "May" must not rewrite "Maybe"."""
    registry = _registry_with(["May"])
    result = registry.anonymize_text("Maybe May will confirm in May.")
    assert result == "Maybe Client_A will confirm in Client_A."


def test_short_client_name_does_not_corrupt_dax():
    """"IT" inside DAX keywords and column names must stay untouched."""
    registry = _registry_with(["IT"])
    dax = 'EVALUATE FILTER(Tickets, Tickets[Priority] = "Critical")'
    assert registry.anonymize_text(dax) == dax


def test_boundary_guard_still_matches_adjacent_punctuation():
    registry = _registry_with(["Acme Corp"])
    result = registry.anonymize_text("Report for Acme Corp's Q3 (Acme Corp).")
    assert "Acme Corp" not in result
    assert "Client_A's" in result
    assert "(Client_A)" in result


def test_entity_ending_in_punctuation_still_matches():
    """Entity values can end with non-word chars, where \\b-style guards fail."""
    registry = _registry_with(["Acme B.V."])
    result = registry.anonymize_text("Invoice sent to Acme B.V. yesterday")
    assert "Acme B.V." not in result
    assert "Client_A" in result


def _resp(*values):
    return {"results": [{"tables": [{"rows": [
        {"[Name]": v} for v in values
    ]}]}]}


def test_generic_service_account_does_not_corrupt_role_name():
    """The regression that motivated never_mask: a contact literally named
    "Desk" rewrote the role "Help Desk" into "Help Contact_1"."""
    registry = EntityRegistry(
        sensitive_columns={"contact": ["'Contacts'[Name]"]},
        dax_executor=lambda q: _resp("Desk", "Jan de Vries"),
    )
    registry.initialize()
    assert registry.anonymize_text("Help Desk") == "Help Desk"
    # the real name beside it is still masked
    assert registry.anonymize_text("Jan de Vries") == "Contact_1"


def test_never_mask_matches_whole_value_not_substring():
    """A company whose name merely contains a generic word is still masked."""
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=lambda q: _resp("Support B.V.", "Admin"),
    )
    registry.initialize()
    assert registry.anonymize("Support B.V.") == "Client_A"
    assert registry.anonymize("Admin") == "Admin"


def test_never_mask_is_case_insensitive():
    registry = EntityRegistry(
        sensitive_columns={"contact": ["'Contacts'[Name]"]},
        dax_executor=lambda q: _resp("ADMIN", "User"),
    )
    registry.initialize()
    assert registry.get_mapping() == {}


def test_never_mask_accepts_extra_values_from_config():
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=lambda q: _resp("Werkplek", "Acme Corp"),
        never_mask=["Werkplek"],
    )
    registry.initialize()
    assert registry.anonymize("Werkplek") == "Werkplek"
    assert registry.anonymize("Acme Corp") == "Client_A"


def test_default_never_mask_can_be_disabled():
    registry = EntityRegistry(
        sensitive_columns={"contact": ["'Contacts'[Name]"]},
        dax_executor=lambda q: _resp("Admin"),
        use_default_never_mask=False,
    )
    registry.initialize()
    assert registry.anonymize("Admin") == "Contact_1"


def test_skipped_values_are_reported_for_audit():
    registry = EntityRegistry(
        sensitive_columns={"contact": ["'Contacts'[Name]"]},
        dax_executor=lambda q: _resp("Admin", "Desk", "Jan de Vries"),
    )
    registry.initialize()
    assert registry.get_skipped() == ["Admin", "Desk"]


def test_alias_numbering_is_not_gapped_by_skips():
    """Skipped values must not consume an alias index."""
    registry = EntityRegistry(
        sensitive_columns={"contact": ["'Contacts'[Name]"]},
        dax_executor=lambda q: _resp("Admin", "Jan de Vries", "User", "Sanne Bakker"),
    )
    registry.initialize()
    assert registry.anonymize("Jan de Vries") == "Contact_1"
    assert registry.anonymize("Sanne Bakker") == "Contact_2"


class _FlakyExecutor:
    """Fails with a rate-limit error the first `fail_times` calls."""

    def __init__(self, fail_times, message="DAX 429: exceeded the amount of requests"):
        self.fail_times = fail_times
        self.message = message
        self.calls = 0

    def __call__(self, query):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(self.message)
        return _resp("Acme Corp")


def test_rate_limited_column_is_retried_and_succeeds():
    ex = _FlakyExecutor(fail_times=2)
    slept = []
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=ex,
        sleep=slept.append,
    )
    registry.initialize()
    assert ex.calls == 3
    assert registry.anonymize("Acme Corp") == "Client_A"
    assert not registry.is_degraded
    assert len(slept) == 2


def test_retry_honours_power_bi_retry_hint():
    ex = _FlakyExecutor(fail_times=1, message="DAX 429: ... Retry in 60 seconds.")
    slept = []
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=ex,
        sleep=slept.append,
    )
    registry.initialize()
    # 60s hint plus up to 1s jitter, not the 2s default base delay
    assert 60 <= slept[0] < 61


def test_non_rate_limit_error_is_not_retried():
    ex = _FlakyExecutor(fail_times=1, message="Column 'Nope' cannot be found")
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=ex,
        sleep=lambda s: None,
        fail_on_degraded=False,
    )
    registry.initialize()
    assert ex.calls == 1
    assert registry.is_degraded


def test_degraded_registry_raises_by_default():
    ex = _FlakyExecutor(fail_times=99)
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=ex,
        max_retries=2,
        sleep=lambda s: None,
    )
    with pytest.raises(RuntimeError, match="registry incomplete"):
        registry.initialize()


def test_degraded_registry_can_be_allowed_explicitly():
    ex = _FlakyExecutor(fail_times=99)
    registry = EntityRegistry(
        sensitive_columns={"client": ["'Companies'[Name]"]},
        dax_executor=ex,
        max_retries=2,
        sleep=lambda s: None,
        fail_on_degraded=False,
    )
    registry.initialize()
    assert registry.is_degraded
    assert registry.failed_columns == ["'Companies'[Name]"]


def test_request_delay_paces_between_columns_but_not_before_first():
    slept = []
    registry = EntityRegistry(
        sensitive_columns={"client": ["'A'[N]", "'B'[N]", "'C'[N]"]},
        dax_executor=lambda q: _resp("Acme Corp"),
        request_delay=0.5,
        sleep=slept.append,
    )
    registry.initialize()
    assert slept == [0.5, 0.5]
