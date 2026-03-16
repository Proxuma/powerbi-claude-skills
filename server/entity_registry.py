"""Deterministic entity anonymization registry.

Loads unique values from Power BI dimension tables and builds a
bidirectional mapping (real value <-> alias). The mapping is consistent
within a session: same input always produces the same alias.
"""

import re
import unicodedata
from typing import Callable, Optional


def _normalize(text: str) -> str:
    """Normalize text for case-insensitive, unicode-safe matching."""
    return unicodedata.normalize("NFC", text.strip().lower())


# Alias prefixes per category
_ALIAS_SCHEMES = {
    "client": lambda i: f"Client_{chr(65 + i)}" if i < 26 else f"Client_{i + 1}",
    "resource": lambda i: f"Resource_{i + 1}",
    "contact": lambda i: f"Contact_{i + 1}",
}


def _default_alias(category: str, index: int) -> str:
    scheme = _ALIAS_SCHEMES.get(category)
    if scheme:
        return scheme(index)
    return f"{category.capitalize()}_{index + 1}"


class EntityRegistry:
    def __init__(
        self,
        sensitive_columns: dict[str, list[str]],
        dax_executor: Callable[[str], dict],
    ):
        """Initialize the registry.

        Args:
            sensitive_columns: Mapping of category to list of DAX column
                references, e.g. {"client": ["'Table'[Col]"]}.
            dax_executor: Function that takes a DAX query string and
                returns the JSON response from Power BI.
        """
        self._sensitive_columns = sensitive_columns
        self._dax_executor = dax_executor
        self._forward: dict[str, str] = {}  # normalized_real_value -> alias
        self._reverse: dict[str, str] = {}  # alias -> original_real_value
        self._sorted_entities: list[tuple[str, str]] = []  # for longest-match-first
        self.is_degraded = False
        self._warnings: list[str] = []

    def initialize(self):
        """Query all sensitive columns and build the mapping."""
        for category, columns in self._sensitive_columns.items():
            counter = 0
            for col_ref in columns:
                try:
                    values = self._fetch_distinct_values(col_ref)
                    for val in values:
                        norm = _normalize(val)
                        if norm and norm not in self._forward:
                            alias = _default_alias(category, counter)
                            self._forward[norm] = alias
                            self._reverse[alias] = val
                            counter += 1
                except Exception as e:
                    self._warnings.append(f"Failed to load {col_ref}: {e}")
                    self.is_degraded = True

        # Sort by length descending for longest-match-first replacement
        self._sorted_entities = sorted(
            [
                (norm, self._reverse[alias])
                for norm, alias in self._forward.items()
            ],
            key=lambda x: len(x[1]),
            reverse=True,
        )

    def _fetch_distinct_values(self, col_ref: str) -> list[str]:
        """Run EVALUATE DISTINCT(...) and extract values."""
        dax = f"EVALUATE DISTINCT({col_ref})"
        result = self._dax_executor(dax)
        values = []
        for table in result.get("results", [{}]):
            for row in table.get("tables", [{}]):
                for entry in row.get("rows", []):
                    for v in entry.values():
                        if v and isinstance(v, str) and v.strip():
                            values.append(v.strip())
        return values

    def anonymize(self, value: str) -> str:
        """Anonymize a single value. Returns alias or original if not found."""
        norm = _normalize(value)
        return self._forward.get(norm, value)

    def deanonymize(self, alias: str) -> str:
        """Reverse an alias back to the real value."""
        return self._reverse.get(alias, alias)

    def anonymize_text(self, text: str) -> str:
        """Replace all known entities in text (longest-match-first, case-insensitive)."""
        if not text or not self._sorted_entities:
            return text
        result = text
        for norm, original in self._sorted_entities:
            alias = self._forward[norm]
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            result = pattern.sub(alias, result)
        return result

    def get_mapping(self) -> dict[str, str]:
        """Return alias -> real_value mapping."""
        return dict(self._reverse)

    def get_warnings(self) -> list[str]:
        """Return list of warnings encountered during initialization."""
        return list(self._warnings)
