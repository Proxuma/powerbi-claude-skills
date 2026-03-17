"""Two-pass anonymizer: deterministic registry + Presidio safety net.

Pass 1: Replace known entities from the EntityRegistry (fast, deterministic).
Pass 2: Run Presidio NLP on remaining text to catch unexpected PII.

The mapping is accumulated across all tool calls in a session.
"""

import re
from typing import Optional

from server.entity_registry import EntityRegistry

# Non-PII values that Presidio incorrectly flags.
# Months, days, priority levels (EN + NL), status names, common business terms.
_PRESIDIO_ALLOWLIST = {
    # English months
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # English days
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Dutch months
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
    # Dutch days
    "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
    # English priority/status names
    "critical", "high", "medium", "low", "urgent", "normal",
    "open", "closed", "complete", "pending", "resolved", "escalated",
    "new", "active", "inactive", "waiting", "scheduled",
    # Dutch priority/status names
    "kritiek", "hoog", "gemiddeld", "laag", "dringend", "normaal",
    "nieuw", "gesloten", "voltooid", "wachtend", "opgelost",
    # Common business terms Presidio misflags
    "ticket", "contract", "project", "service", "support",
    "backup", "patch", "alert", "device", "endpoint",
    "client", "resource", "server", "completed", "cancelled",
    "none",
}


# Dutch tussenvoegsels for regex
_DUTCH_NAME_PATTERNS = [
    # "Pieter van den Berg", "Maria van de Pol", "Jan van het Veld"
    re.compile(
        r"\b[A-Z][a-z]+ (?:van (?:de[rn]?|het)|de|den|het|op de|in 't|van 't|ter|ten) [A-Z][a-z]+(?:-[A-Z][a-z]+)?\b"
    ),
    # "Jan-Willem de Groot"
    re.compile(
        r"\b[A-Z][a-z]+-[A-Z][a-z]+ (?:van (?:de[rn]?|het)|de|den|het|op de|in 't|van 't|ter|ten) [A-Z][a-z]+\b"
    ),
    # "P. van den Berg"
    re.compile(
        r"\b[A-Z]\.\s?(?:van (?:de[rn]?|het)|de|den|het|op de|in 't|van 't|ter|ten) [A-Z][a-z]+\b"
    ),
]


class Anonymizer:
    def __init__(
        self,
        registry: EntityRegistry,
        presidio_enabled: bool = True,
        enabled: bool = True,
    ):
        self._registry = registry
        self._presidio_enabled = presidio_enabled
        self._enabled = enabled
        self._presidio_mapping: dict[str, str] = {}   # alias -> real value
        self._presidio_counter: dict[str, int] = {}    # entity_type -> counter
        self._analyzer = None
        self._anonymizer_engine = None

    # ------------------------------------------------------------------
    # Presidio lazy loading
    # ------------------------------------------------------------------

    def _get_presidio(self):
        """Lazy-load Presidio engines (heavy imports deferred to first use)."""
        if self._analyzer is None:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine

            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
            })
            nlp_engine = provider.create_engine()
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self._anonymizer_engine = AnonymizerEngine()
        return self._analyzer, self._anonymizer_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anonymize_text(self, text: str) -> str:
        """Three-pass anonymization on a text string."""
        if not self._enabled or not text or not isinstance(text, str):
            return text

        # Pass 1: deterministic replacement via EntityRegistry
        result = self._registry.anonymize_text(text)

        # Pass 2: Presidio NLP safety net
        if self._presidio_enabled:
            result = self._presidio_pass(result)

        # Pass 3: Dutch name regex
        result = self._dutch_name_pass(result)

        return result

    def anonymize_json(self, data):
        """Recursively anonymize all string values in a JSON-like structure."""
        if not self._enabled:
            return data
        if isinstance(data, str):
            return self.anonymize_text(data)
        elif isinstance(data, dict):
            return {k: self.anonymize_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.anonymize_json(item) for item in data]
        return data

    def get_full_mapping(self) -> dict[str, str]:
        """Return combined mapping: registry aliases + Presidio detections."""
        mapping = dict(self._registry.get_mapping())
        mapping.update(self._presidio_mapping)
        return mapping

    def get_stats(self) -> dict:
        return {
            "registry_entities": len(self._registry.get_mapping()),
            "presidio_detections": len(self._presidio_mapping),
            "is_degraded": self._registry.is_degraded,
            "warnings": self._registry.get_warnings(),
        }

    # ------------------------------------------------------------------
    # Presidio pass internals
    # ------------------------------------------------------------------

    def _presidio_pass(self, text: str) -> str:
        """Run Presidio NER and replace detections with indexed tokens."""
        analyzer, _ = self._get_presidio()

        results = analyzer.analyze(text=text, language="en", score_threshold=0.7)
        if not results:
            return text

        # Sort by start position descending so replacements don't shift offsets
        results = sorted(results, key=lambda r: r.start, reverse=True)

        for detection in results:
            original = text[detection.start:detection.end]

            # Skip values already replaced by Pass 1
            if self._is_already_aliased(original):
                continue

            # Skip known non-PII values (months, priorities, etc.)
            if original.strip().lower() in _PRESIDIO_ALLOWLIST:
                continue

            # Reuse existing alias for the same detected value
            existing = self._find_existing_presidio_alias(original)
            if existing:
                alias = existing
            else:
                entity_type = detection.entity_type
                count = self._presidio_counter.get(entity_type, 0)
                self._presidio_counter[entity_type] = count + 1
                alias = f"<{entity_type}_{count + 1}>"
                self._presidio_mapping[alias] = original

            text = text[:detection.start] + alias + text[detection.end:]

        return text

    def _dutch_name_pass(self, text: str) -> str:
        """Detect and anonymize Dutch compound names with tussenvoegsels."""
        for pattern in _DUTCH_NAME_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group()
                if name.lower() in _PRESIDIO_ALLOWLIST:
                    continue
                if self._is_already_aliased(name):
                    continue
                alias = self._find_existing_presidio_alias(name)
                if alias is None:
                    idx = len(self._presidio_mapping) + 1
                    alias = f"<DUTCH_NAME_{idx}>"
                    self._presidio_mapping[alias] = name
                text = text.replace(name, alias)
        return text

    def _is_already_aliased(self, text: str) -> bool:
        """Check if text looks like an alias produced by Pass 1."""
        return bool(re.match(
            r'^(Client_[A-Z0-9]+|Resource_\d+|Contact_\d+)$', text,
        ))

    def _find_existing_presidio_alias(self, original: str) -> Optional[str]:
        """Return an existing Presidio alias for the same real value, if any."""
        norm = original.strip().lower()
        for alias, real in self._presidio_mapping.items():
            if real.strip().lower() == norm:
                return alias
        return None
