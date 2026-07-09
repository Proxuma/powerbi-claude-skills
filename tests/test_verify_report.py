"""Tests for tools/verify_report.py — the customer-facing DAX verifier.

Extraction and comparison are covered offline with fixture HTML that mimics
both report families: powerbireport.md dax-toggle blocks and QBR
dax-proof details. Execution against a live tenant is exercised through an
injected fake executor; the real-network test is skipped by default like the
Presidio tests (set POWERBI_VERIFY_LIVE=1 to run it).
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import verify_report  # noqa: E402


# HTML-escaped queries, exactly as generated reports carry them: &lt; &gt;
# &amp; in DAX and Presidio aliases like &lt;PERSON_1&gt;.
FIXTURE_HTML = """
<html><body>
<h2>Ticket volume</h2>
<div class="dax-toggle" onclick="this.classList.toggle('expanded')">
  <div class="dax-trigger">
    <svg class="dax-chevron"></svg>
    <span>View DAX Query — Total tickets</span>
  </div>
  <div class="dax-content">
    <pre><code>EVALUATE ROW("total_tickets", COUNTROWS(FILTER('Tickets', 'Tickets'[age] &gt;= 0 &amp;&amp; 'Tickets'[age] &lt; 999)))
-- Result: total_tickets = 1,284</code></pre>
    <button class="dax-copy">Copy Query</button>
  </div>
</div>

<h2>SLA</h2>
<div class="dax-toggle">
  <div class="dax-trigger"><span>View DAX Query — SLA compliance</span></div>
  <div class="dax-content">
    <pre><code>EVALUATE ROW("sla_pct", [SLA Compliance])
-- Result: sla_pct = 93%</code></pre>
  </div>
</div>

<section data-screen-label="Service desk">
  <details class="dax-proof"><summary>DAX query</summary><pre>
EVALUATE ROW("avg_resolution_days", [Avg Resolution])
-- Result: avg_resolution_days = 4.7
  </pre></details>
</section>

<section data-screen-label="Top client">
  <details class="dax-proof"><summary>DAX query</summary><pre>
EVALUATE FILTER('Companies', 'Companies'[name] = "Client_A" &amp;&amp; 'Companies'[owner] = "&lt;PERSON_1&gt;")
  </pre></details>
</section>
</body></html>
"""


@pytest.fixture
def panels():
    return verify_report.extract_panels(FIXTURE_HTML)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_extracts_both_families(panels):
    assert len(panels) == 4
    assert [p["family"] for p in panels] == [
        "dax-toggle", "dax-toggle", "dax-proof", "dax-proof"]


def test_section_labels(panels):
    assert panels[0]["section"] == "Total tickets"
    assert panels[1]["section"] == "SLA compliance"
    assert panels[2]["section"] == "Service desk"
    assert panels[3]["section"] == "Top client"


def test_queries_are_html_unescaped(panels):
    assert "'Tickets'[age] >= 0 && 'Tickets'[age] < 999" in panels[0]["query"]
    assert '"<PERSON_1>"' in panels[3]["query"]
    assert "&lt;" not in panels[3]["query"]
    assert "&amp;" not in panels[0]["query"]


def test_result_comments_stripped_from_query(panels):
    for p in panels:
        assert "-- Result" not in p["query"]


def test_expected_values_parsed(panels):
    assert panels[0]["expected"] == [(1284.0, 0, False)]
    assert panels[1]["expected"] == [(93.0, 0, True)]
    assert panels[2]["expected"] == [(4.7, 1, False)]
    assert panels[3]["expected"] == []


def test_dutch_result_comment_supported():
    html = ('<details class="dax-proof"><pre>EVALUATE ROW("n", 1)\n'
            '-- Resultaat: n = 42</pre></details>')
    panels = verify_report.extract_panels(html)
    assert panels[0]["expected"] == [(42.0, 0, False)]
    assert panels[0]["query"] == 'EVALUATE ROW("n", 1)'


def test_no_panels_in_plain_html():
    assert verify_report.extract_panels("<html><pre>SELECT 1</pre></html>") == []


# ---------------------------------------------------------------------------
# Number parsing
# ---------------------------------------------------------------------------

def test_parse_plain_and_thousands():
    assert verify_report.parse_numbers("total = 1,284") == [(1284.0, 0, False)]
    assert verify_report.parse_numbers("rows: 1,234,567") == [(1234567.0, 0, False)]


def test_parse_decimal_and_percent():
    assert verify_report.parse_numbers("avg = 4.7") == [(4.7, 1, False)]
    assert verify_report.parse_numbers("sla 93%") == [(93.0, 0, True)]


def test_parse_currency_and_mixed_separators():
    assert verify_report.parse_numbers("revenue € 1.234,56") == [(1234.56, 2, False)]
    assert verify_report.parse_numbers("$1,234.56") == [(1234.56, 2, False)]


def test_parse_negative_and_multiple():
    nums = verify_report.parse_numbers("delta -12.5 on 3 tickets")
    assert (-12.5, 1, False) in nums
    assert (3.0, 0, False) in nums


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def test_diff_matches_with_rounding():
    # Report shows 4.7, model returns 4.7143 — that is the same number at
    # the precision the report displays.
    assert verify_report.diff_expected([(4.7, 1, False)], [4.7143]) == []


def test_diff_percent_matches_fraction_and_whole():
    assert verify_report.diff_expected([(93.0, 0, True)], [0.9331]) == []
    assert verify_report.diff_expected([(93.0, 0, True)], [93.2]) == []


def test_diff_reports_missing_value():
    missing = verify_report.diff_expected([(1284.0, 0, False)], [1290.0, 4.7])
    assert missing == [(1284.0, 0, False)]


def test_collect_returned_values_flattens_rows():
    response = {"results": [{"tables": [{"rows": [
        {"[n]": 550, "[name]": "Acme", "[pct]": "0.93"}]}]}]}
    assert verify_report.collect_returned_values(response) == [550.0, 0.93]


# ---------------------------------------------------------------------------
# Verification with an injected executor (no network)
# ---------------------------------------------------------------------------

def _response(*values):
    return {"results": [{"tables": [{"rows": [
        {f"[v{i}]": v for i, v in enumerate(values)}]}]}]}


def test_verify_pass_fail_and_error(panels):
    def executor(query):
        if "total_tickets" in query:
            return _response(1284)
        if "sla_pct" in query:
            return _response(0.93)
        if "avg_resolution_days" in query:
            return _response(9.9)  # doctored: report says 4.7
        raise RuntimeError("table not found")

    results = verify_report.verify_panels(panels, executor)
    statuses = {r["section"]: r["status"] for r in results}
    assert statuses["Total tickets"] == "PASS"
    assert statuses["SLA compliance"] == "PASS"
    assert statuses["Service desk"] == "FAIL"
    assert statuses["Top client"] == "ERROR"
    fail = next(r for r in results if r["status"] == "FAIL")
    assert "4.7" in fail["detail"]


def test_verify_without_expected_values_is_exec_only():
    html = '<details class="dax-proof"><pre>EVALUATE ROW("n", 1)</pre></details>'
    panels = verify_report.extract_panels(html)
    results = verify_report.verify_panels(panels, lambda q: _response(1))
    assert results[0]["status"] == "PASS"
    assert results[0]["value_checked"] is False


def test_verify_rewrites_alias_literals_before_execution(panels):
    seen = {}

    def executor(query):
        seen[query.split('"')[1]] = query
        return _response(1284, 0.93, 4.7)

    mapping = {"Client_A": "Acme & Zonen BV", "<PERSON_1>": "Piet Janssen"}
    results = verify_report.verify_panels(panels, executor, mapping)
    top_client = next(r for r in results if r["section"] == "Top client")
    assert top_client["aliases_rewritten"] == 2
    executed = next(q for q in seen.values() if "Companies" in q)
    assert '"Acme & Zonen BV"' in executed
    assert '"Piet Janssen"' in executed
    assert "Client_A" not in executed


# ---------------------------------------------------------------------------
# Live execution (skipped by default, like the Presidio tests)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("POWERBI_VERIFY_LIVE") != "1",
                    reason="live tenant test; set POWERBI_VERIFY_LIVE=1 to run")
def test_live_executor_runs_trivial_query():
    dataset_id = verify_report.resolve_dataset_id(None)
    assert dataset_id, "no dataset configured"
    executor = verify_report.make_live_executor(dataset_id)
    response = executor('EVALUATE ROW("n", 1+1)')
    assert verify_report.collect_returned_values(response) == [2.0]


# ---------------------------------------------------------------------------
# dax-query family (projectreport) — new extractor path
# ---------------------------------------------------------------------------

DAXQUERY_HTML = """
<div class="section-label"><span>DAX Queries - Data Verification</span></div>
<div class="dax-query">
  <div class="dax-header" onclick="this.parentElement.classList.toggle('expanded')">
    <span class="dax-title">1. Project Details</span>
    <span class="dax-toggle-icon">&#9660;</span>
  </div>
  <div class="dax-content">
    <pre><code>EVALUATE FILTER('BI_Autotask_Projects', 'BI_Autotask_Projects'[project_id] = 8)</code></pre>
    <button class="copy-btn">Copy Query</button>
  </div>
</div>
<div class="dax-query">
  <div class="dax-header">
    <span class="dax-title">2. Phase Summary</span>
    <span class="dax-toggle-icon">&#9660;</span>
  </div>
  <div class="dax-content">
    <pre><code>EVALUATE SUMMARIZECOLUMNS('Tasks'[phase], "Worked", SUM('Tasks'[worked_hours]))</code></pre>
  </div>
</div>
"""


def test_dax_query_family_extracted():
    panels = verify_report.extract_panels(DAXQUERY_HTML)
    assert [p["family"] for p in panels] == ["dax-query", "dax-query"]
    assert panels[0]["section"] == "1. Project Details"
    assert panels[1]["section"] == "2. Phase Summary"
    assert panels[0]["query"].startswith("EVALUATE FILTER('BI_Autotask_Projects'")


def test_dax_query_without_result_is_execute_only():
    panels = verify_report.extract_panels(DAXQUERY_HTML)
    assert all(p["expected"] == [] for p in panels)
    results = verify_report.verify_panels(panels, lambda q: _response(8))
    assert all(r["status"] == "PASS" for r in results)
    assert all(r["value_checked"] is False for r in results)


# ---------------------------------------------------------------------------
# Multi-EVALUATE splitting (QBR proof panels)
# ---------------------------------------------------------------------------

MULTI_EVALUATE_HTML = """
<section data-screen-label="Service delivery">
  <details class="dax-proof"><summary>DAX</summary><pre>
// tickets by type
EVALUATE SUMMARIZECOLUMNS('Tickets'[type], "n", COUNTROWS('Tickets'))
-- Result: Incident 953; Change 103; Problem 2 (total 1058)

// contracts on file
EVALUATE ROW("Total", 6, "Active", 5)
-- Result: TotalContracts = 6; ActiveContracts = 5
  </pre></details>
</section>
"""


def test_multi_evaluate_panel_splits_into_statements():
    panels = verify_report.extract_panels(MULTI_EVALUATE_HTML)
    assert len(panels) == 2
    assert panels[0]["section"] == "Service delivery (1/2)"
    assert panels[1]["section"] == "Service delivery (2/2)"
    # Each statement carries only its own EVALUATE.
    assert panels[0]["query"].count("EVALUATE") == 1
    assert panels[1]["query"].count("EVALUATE") == 1
    assert "SUMMARIZECOLUMNS" in panels[0]["query"]
    assert '"Total", 6' in panels[1]["query"]


def test_split_dax_statements_direct():
    text = ('// c1\nEVALUATE ROW("a", 1)\n-- Result: a = 1\n'
            'EVALUATE ROW("b", 2)\n-- Result: b = 2')
    parts = verify_report.split_dax_statements(text)
    assert len(parts) == 2
    assert "ROW(\"a\", 1)" in parts[0]
    assert "ROW(\"b\", 2)" in parts[1]


def test_split_keeps_define_with_its_evaluate():
    text = ('DEFINE VAR x = 1\nEVALUATE ROW("a", x)\n'
            'EVALUATE ROW("b", 2)')
    parts = verify_report.split_dax_statements(text)
    assert len(parts) == 2
    assert parts[0].strip().startswith("DEFINE")
    assert "ROW(\"a\", x)" in parts[0]
    assert parts[1].strip().startswith("EVALUATE")


def test_single_statement_not_split():
    text = 'EVALUATE ROW("a", 1)\n-- Result: a = 1'
    assert verify_report.split_dax_statements(text) == [text]


# ---------------------------------------------------------------------------
# Number parsing: digits in words, product names, calendar labels
# ---------------------------------------------------------------------------

def test_digits_glued_to_letters_are_not_numbers():
    # "M365" abbreviation and "Q2"/"P4" tier codes are not the numbers 365/2/4,
    # and the digit after the rejected letter does not start a fresh match.
    assert verify_report.parse_numbers("no per-company M365 data (0)") == [(0.0, 0, False)]
    assert verify_report.parse_numbers("Q2 2026 created = 305") == [(305.0, 0, False)]
    assert verify_report.parse_numbers("tier P4 volume = 14") == [(14.0, 0, False)]


def test_microsoft_365_product_name_is_not_a_number():
    assert verify_report.parse_numbers("Microsoft 365") == []
    assert verify_report.parse_numbers("Microsoft 365 seats = 42") == [(42.0, 0, False)]
    assert verify_report.parse_numbers("Office 365 users: 5") == [(5.0, 0, False)]


def test_calendar_labels_are_not_numbers():
    assert verify_report.parse_numbers("last create date = 21 Jan 2026") == []
    assert verify_report.parse_numbers("window Aug 2025 to Jan 2026") == []
    assert verify_report.parse_numbers("since 2025 the count = 100") == [(100.0, 0, False)]
    assert verify_report.parse_numbers("iso 2026-01-21 total 7") == [(7.0, 0, False)]


# ---------------------------------------------------------------------------
# Derived values: null-as-zero, column totals, complements, percentages
# ---------------------------------------------------------------------------

def test_null_cells_count_as_zero():
    response = {"results": [{"tables": [{"rows": [{"[x]": None, "[y]": 5}]}]}]}
    assert verify_report.collect_returned_values(response) == [0.0, 5.0]


def test_collect_derived_column_total_and_complement():
    # A single column over several rows: its total is derivable.
    total = {"results": [{"tables": [{"rows": [
        {"[n]": 953}, {"[n]": 103}, {"[n]": 2}]}]}]}
    assert 1058.0 in verify_report.collect_derived_values(total)
    # Two column totals: their difference (a complement) is derivable.
    two = {"results": [{"tables": [{"rows": [{"[Total]": 218, "[Managed]": 166}]}]}]}
    derived = verify_report.collect_derived_values(two)
    assert 52.0 in derived and 218.0 in derived and 166.0 in derived


def test_derived_percentage_and_complement_do_not_fail_panel():
    html = ('<section data-screen-label="Cyber">'
            '<details class="dax-proof"><pre>'
            'EVALUATE ROW("TotalAssets", 218, "RMM_managed", 166)\n'
            '-- Result: TotalAssets = 218; RMM_managed = 166 (76%); unmanaged = 52'
            '</pre></details></section>')
    panels = verify_report.extract_panels(html)
    results = verify_report.verify_panels(
        panels, lambda q: {"results": [{"tables": [{"rows": [
            {"[TotalAssets]": 218, "[RMM_managed]": 166}]}]}]})
    r = results[0]
    assert r["status"] == "PASS"
    assert set(r["derived"]) == {"76%", "52"}
    assert r["value_checked"] is True


def test_plain_unmatched_number_still_fails():
    # A non-percent, non-derivable value the query should have returned but did
    # not is a real mismatch, not softened away.
    html = ('<details class="dax-proof"><pre>EVALUATE ROW("avg", 1)\n'
            '-- Result: avg = 4.7</pre></details>')
    panels = verify_report.extract_panels(html)
    results = verify_report.verify_panels(panels, lambda q: _response(9.9))
    assert results[0]["status"] == "FAIL"
    assert "4.7" in results[0]["detail"]
