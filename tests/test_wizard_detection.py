"""Tests for the wizard's sensitive-column detection and self-test.

The column names below come from the live Proxuma data model template,
which is snake_case throughout. The original regex only matched spaced
or CamelCase names, so every one of these real columns went undetected.
"""

import pytest

from server.wizard import classify_column, run_anonymization_self_test


# Real columns from the Proxuma template model that MUST be detected.
REAL_MODEL_COLUMNS = [
    ("company_name", "client"),
    ("account_name", "client"),
    ("owner_resource_name", "resource"),
    ("created_by_resource_name", "resource"),
    ("creator_resource_name", "resource"),
    ("primary_contact_name", "contact"),
    ("contact_name", "contact"),
    ("email_address", "contact"),
    ("first_name", "contact"),
    ("last_name", "contact"),
]

# Columns that must NOT be flagged: ids, metrics, and generic *_name
# columns that carry no person or company data.
NON_SENSITIVE_COLUMNS = [
    "company_id",
    "resource_id",
    "contact_id",
    "account_id",
    "id",
    "ticket_number",
    "created_date",
    "month_name",
    "status_name",
    "queue_name",
    "revenue",
]

# The spaced / CamelCase names the old regex handled must keep working.
LEGACY_COLUMNS = [
    ("Company Name", "client"),
    ("CompanyName", "client"),
    ("Full Name", "contact"),
    ("FullName", "contact"),
    ("Email", "contact"),
    ("Phone", "contact"),
]


@pytest.mark.parametrize("column,expected", REAL_MODEL_COLUMNS)
def test_snake_case_columns_detected(column, expected):
    assert classify_column(column) == expected


@pytest.mark.parametrize("column", NON_SENSITIVE_COLUMNS)
def test_non_sensitive_columns_not_flagged(column):
    assert classify_column(column) is None


@pytest.mark.parametrize("column,expected", LEGACY_COLUMNS)
def test_legacy_naming_still_detected(column, expected):
    assert classify_column(column) == expected


def _dax_response(values):
    """Shape a fake executeQueries response the registry can parse."""
    return {"results": [{"tables": [{"rows": [{"[c]": v} for v in values]}]}]}


def test_self_test_prints_before_after(capsys):
    executor = lambda query: _dax_response(["Acme BV", "Globex NV"])
    ok = run_anonymization_self_test(
        {"client": ["'BI_Companies'[company_name]"]},
        dax_executor=executor,
    )
    assert ok is True
    out = capsys.readouterr().out
    assert "Acme BV" in out
    assert "Client_A" in out


def test_self_test_warns_loudly_on_zero_entities(capsys):
    executor = lambda query: {"results": []}
    ok = run_anonymization_self_test(
        {"client": ["'BI_Companies'[company_name]"]},
        dax_executor=executor,
    )
    assert ok is False
    out = capsys.readouterr().out
    assert "0 entities" in out
    assert "WILL reach the AI" in out


def test_self_test_samples_with_topn():
    queries = []

    def executor(query):
        queries.append(query)
        return _dax_response(["Acme BV"])

    run_anonymization_self_test(
        {"client": ["'BI_Companies'[company_name]"]},
        dax_executor=executor,
    )
    assert queries == [
        "EVALUATE TOPN(3, DISTINCT('BI_Companies'[company_name]))"
    ]


def test_self_test_fails_when_no_candidates(capsys):
    ok = run_anonymization_self_test({}, dax_executor=lambda q: {})
    assert ok is False


# --- TMDL part-path parsing -------------------------------------------------
# Real getDefinition responses use flat paths (definition/tables/X.tmdl).
# The original pattern required a slash after the table name, so it matched
# nothing on a real model and detection returned {} while anonymization
# reported itself enabled.

from server.wizard import table_from_path


@pytest.mark.parametrize("path,expected", [
    ("definition/tables/BI_Autotask_Companies.tmdl", "BI_Autotask_Companies"),
    ("definition/tables/BI_Autotask_Companies/columns.tmdl", "BI_Autotask_Companies"),
    ("definition/tables/My.Table.tmdl", "My.Table"),
    ("definition/model.tmdl", None),
    ("definition/relationships.tmdl", None),
])
def test_table_from_path(path, expected):
    assert table_from_path(path) == expected


# --- Unprotected-column warn pass ------------------------------------------
# A second, warn-only scan flags columns that carry identifying or
# re-identifying information but are NEVER auto-anonymized: free-text fields
# (only screened when Presidio/Pass 2 is installed) and descriptive columns
# (role/sector/title, never masked). classify_unprotected_column does not add
# anything to sensitive_columns; it only surfaces columns the user must review.

from server.wizard import (
    classify_unprotected_column,
    warn_unprotected_columns,
)


# Free-text columns that must be flagged as 'free_text'.
FREE_TEXT_COLUMNS = [
    "description",
    "contract_description",
    "desc",
    "note",
    "internal_notes",
    "summary_notes",
    "comment",
    "summary",
    "subject",
    "ticket_title",
    "title",
    "body",
    "detail",
    "resolution_details",
    "resolution",
]

# Descriptive / re-identifying columns that must be flagged as 'descriptive'.
DESCRIPTIVE_COLUMNS = [
    "role_name",
    "role",
    "specialty",
    "speciality",
    "job_title",
    "jobtitle",
    "department",
    "sector",
    "industry",
]

# Columns the warn pass must stay silent on: ids, metrics, and the
# name/email/phone columns already handled by classify_column.
UNPROTECTED_NONE_COLUMNS = [
    "company_id",
    "resource_id",
    "ticket_number",
    "created_date",
    "revenue",
    "hours",
    "company_name",
    "first_name",
    "email_address",
    "primary_contact_name",
    "status_name",
    "queue_name",
]


@pytest.mark.parametrize("column", FREE_TEXT_COLUMNS)
def test_free_text_columns_flagged(column):
    assert classify_unprotected_column(column) == "free_text"


@pytest.mark.parametrize("column", DESCRIPTIVE_COLUMNS)
def test_descriptive_columns_flagged(column):
    assert classify_unprotected_column(column) == "descriptive"


@pytest.mark.parametrize("column", UNPROTECTED_NONE_COLUMNS)
def test_unprotected_pass_ignores_ids_metrics_and_sensitive(column):
    assert classify_unprotected_column(column) is None


def test_warn_pass_prints_when_columns_present(capsys):
    printed = warn_unprotected_columns({
        "free_text": ["'Tickets'[description]"],
        "descriptive": ["'Resources'[role_name]"],
    })
    assert printed is True
    out = capsys.readouterr().out
    assert "'Tickets'[description]" in out
    assert "'Resources'[role_name]" in out
    assert "NOT auto-anonymized" in out
    assert "Presidio" in out
    assert "sensitive_columns" in out


def test_warn_pass_silent_when_no_columns(capsys):
    printed = warn_unprotected_columns({})
    assert printed is False
    assert capsys.readouterr().out == ""
