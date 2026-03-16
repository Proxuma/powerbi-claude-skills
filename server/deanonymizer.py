"""Deanonymize reports by reversing alias mappings.

Three entry points:
1. deanonymize_text() -- replace aliases in a string
2. deanonymize_html() -- replace aliases in HTML with XSS protection
3. deanonymize_file() -- read HTML + mapping files, write output
"""

import html
import json
from pathlib import Path


def deanonymize_text(text: str, mapping: dict[str, str]) -> str:
    """Replace all aliases with real values. Longest alias first."""
    if not text or not mapping:
        return text
    sorted_aliases = sorted(mapping.keys(), key=len, reverse=True)
    result = text
    for alias in sorted_aliases:
        result = result.replace(alias, mapping[alias])
    return result


def deanonymize_html(html_text: str, mapping: dict[str, str]) -> str:
    """Replace aliases in HTML, HTML-escaping real values to prevent XSS."""
    if not html_text or not mapping:
        return html_text
    safe_mapping = {alias: html.escape(real) for alias, real in mapping.items()}
    return deanonymize_text(html_text, safe_mapping)


def deanonymize_file(html_path: Path, mapping_path: Path, output_path: Path):
    """Read HTML + mapping, write deanonymized output."""
    html_text = html_path.read_text(encoding="utf-8")
    with open(mapping_path, encoding="utf-8") as f:
        data = json.load(f)
    mapping = data.get("mappings", data)
    result = deanonymize_html(html_text, mapping)
    output_path.write_text(result, encoding="utf-8")
