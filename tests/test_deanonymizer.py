import json
import tempfile

import pytest
from pathlib import Path
from server.deanonymizer import deanonymize_html, deanonymize_text, deanonymize_file


def test_deanonymize_text_replaces_aliases():
    mapping = {"Client_A": "Acme Corp", "Resource_1": "Jan de Vries"}
    text = "Client_A ticket assigned to Resource_1"
    result = deanonymize_text(text, mapping)
    assert result == "Acme Corp ticket assigned to Jan de Vries"


def test_deanonymize_text_replaces_presidio_tokens():
    mapping = {"<PERSON_1>": "Sarah Connor", "<EMAIL_ADDRESS_1>": "sarah@sky.net"}
    text = "Contact <PERSON_1> at <EMAIL_ADDRESS_1>"
    result = deanonymize_text(text, mapping)
    assert result == "Contact Sarah Connor at sarah@sky.net"


def test_deanonymize_text_empty_inputs():
    assert deanonymize_text("", {"a": "b"}) == ""
    assert deanonymize_text("hello", {}) == "hello"
    assert deanonymize_text("", {}) == ""


def test_deanonymize_text_longest_alias_first():
    mapping = {"Client": "Short", "Client_Alpha": "Long Name"}
    text = "Client_Alpha and Client"
    result = deanonymize_text(text, mapping)
    assert result == "Long Name and Short"


def test_deanonymize_html_full_roundtrip():
    mapping = {"Client_A": "Acme Corp", "Resource_1": "Jan de Vries"}
    html_text = """<html><body>
    <h1>Report for Client_A</h1>
    <p>Prepared by Resource_1</p>
    <pre><code>EVALUATE SUMMARIZECOLUMNS('Table'[Col])</code></pre>
    </body></html>"""
    result = deanonymize_html(html_text, mapping)
    assert "Acme Corp" in result
    assert "Jan de Vries" in result
    assert "Client_A" not in result
    assert "EVALUATE SUMMARIZECOLUMNS" in result


def test_deanonymize_html_escapes_html_entities():
    mapping = {"Client_A": '<script>alert("xss")</script>'}
    html_text = "<p>Report for Client_A</p>"
    result = deanonymize_html(html_text, mapping)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_deanonymize_html_escapes_ampersand():
    mapping = {"Client_A": "Tom & Jerry"}
    html_text = "<p>Client_A</p>"
    result = deanonymize_html(html_text, mapping)
    assert "Tom &amp; Jerry" in result


def test_deanonymize_html_empty_inputs():
    assert deanonymize_html("", {"a": "b"}) == ""
    assert deanonymize_html("<p>hi</p>", {}) == "<p>hi</p>"


def test_deanonymize_from_file():
    mapping = {"Client_A": "Acme Corp"}
    with tempfile.TemporaryDirectory() as tmpdir:
        mapping_path = Path(tmpdir) / "mapping.json"
        with open(mapping_path, "w") as f:
            json.dump({"mappings": mapping}, f)
        html_path = Path(tmpdir) / "report.html"
        html_path.write_text("<p>Client_A data</p>")
        output_path = Path(tmpdir) / "report-final.html"
        deanonymize_file(html_path, mapping_path, output_path)
        result = output_path.read_text()
        assert "Acme Corp" in result
        assert "Client_A" not in result


def test_deanonymize_from_file_flat_mapping():
    """Test with a flat mapping dict (no 'mappings' wrapper)."""
    mapping = {"Resource_1": "Jan de Vries"}
    with tempfile.TemporaryDirectory() as tmpdir:
        mapping_path = Path(tmpdir) / "mapping.json"
        with open(mapping_path, "w") as f:
            json.dump(mapping, f)
        html_path = Path(tmpdir) / "report.html"
        html_path.write_text("<p>Resource_1 report</p>")
        output_path = Path(tmpdir) / "output.html"
        deanonymize_file(html_path, mapping_path, output_path)
        result = output_path.read_text()
        assert "Jan de Vries" in result
        assert "Resource_1" not in result
