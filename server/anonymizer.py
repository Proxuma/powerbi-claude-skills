"""Two-pass anonymizer: deterministic registry + Presidio safety net.

Pass 1: Replace known entities from the EntityRegistry (fast, deterministic).
Pass 2: Run Presidio NLP on remaining text to catch unexpected PII.

The mapping is accumulated across all tool calls in a session.
"""

import re
import sys
from typing import Optional

from server.entity_registry import EntityRegistry

PRESIDIO_INSTALL_HINT = (
    "pip install presidio-analyzer presidio-anonymizer spacy "
    "&& python -m spacy download en_core_web_sm"
)

# Non-PII values that Presidio incorrectly flags.
# Months, days, priority levels (EN + NL), status names, common business terms,
# and DAX / schema identifiers that Presidio's NER reads as organisations.
_PRESIDIO_ALLOWLIST = {
    # English months
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # English days
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
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
    # Schema / measure words the E2E saw masked as <ORGANIZATION_x>
    "hours", "ratio", "sla", "count", "sum", "total", "average", "avg",
    "snapshot", "queue", "queues", "resource", "resources", "capacity",
    # DAX function names (Presidio NER tags these as organisations)
    "divide", "calculate", "filter", "sumx", "countx", "countrows",
    "distinctcount", "averagex", "maxx", "minx", "rankx", "topn", "related",
    "summarize", "summarizecolumns", "addcolumns", "selectedvalue",
    "isblank", "switch", "values", "allexcept", "dateadd", "datesytd",
    "totalytd", "earlier", "coalesce", "format", "concatenate", "concatenatex",
}

# Entity types Pass 2 (Presidio) masks by default. Notably EXCLUDES DATE_TIME:
# masking dates broke data-end discovery in the E2E (MAX(create_date) returned a
# token). Override per install with anonymization.presidio_entities in config.
_DEFAULT_PRESIDIO_ENTITIES = (
    "PERSON", "ORGANIZATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
    "NRP", "CREDIT_CARD", "IBAN_CODE", "US_SSN", "US_BANK_NUMBER",
    "US_DRIVER_LICENSE", "US_PASSPORT", "IP_ADDRESS", "CRYPTO",
    "MEDICAL_LICENSE", "URL",
)

# Entity types whose value is meant to be numeric; a pure-number detection here
# is real PII (a phone, a card), so the numeric skip-rule must not touch them.
_NUMERIC_PII_ENTITIES = frozenset({
    "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "US_SSN", "US_BANK_NUMBER",
    "IP_ADDRESS", "CRYPTO",
})

# A full GUID (8-4-4-4-12) or a bare hex id fragment: never PII. The hex
# fragment must contain at least one a-f letter, so a plain number (e.g. a phone
# number of only digits) is left to the numeric rule, which respects PII types.
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HEX_ID_RE = re.compile(r"^(?=[0-9a-f]*[a-f])[0-9a-f]{8,}$", re.I)

# A pure number or an ISO date/datetime: digits with only separators around them.
_NUMERIC_OR_DATE_RE = re.compile(r"^\d[\dT.,:/ \-]*$")

# Categorical labels recognisable by shape, so we do not hardcode every Dutch
# variant. ^P[1-4] covers priority tiers (P1-Kritisch, P2-Hoog, P3-Medium, ...).
_PRESIDIO_SKIP_PATTERNS = (
    re.compile(r"^P[1-4]\b", re.I),
)


def _is_presidio_false_positive(text: str, entity_type: str) -> bool:
    """True if a Pass 2 detection is clearly not PII and should not be aliased.

    Reduces over-masking in the safe direction only: GUIDs/hex ids, pure
    numbers and ISO dates (except for entities that are legitimately numeric,
    like phone numbers), DAX/schema keywords, and shape-matched categorical
    labels. When in doubt this returns False and the value stays masked.
    """
    s = text.strip()
    if not s:
        return True
    if s.lower() in _PRESIDIO_ALLOWLIST:
        return True
    if _GUID_RE.match(s) or _HEX_ID_RE.match(s):
        return True
    if entity_type not in _NUMERIC_PII_ENTITIES and _NUMERIC_OR_DATE_RE.match(s):
        return True
    return any(p.match(s) for p in _PRESIDIO_SKIP_PATTERNS)


# Aliases produced by Pass 1 (registry) and Pass 2 (Presidio tokens like <PERSON_1>).
_DAX_ALIAS = re.compile(
    r'Client_[A-Z0-9]+|Resource_\d+|Contact_\d+|Workspace_\d+|Dataset_\d+'
    r'|<[A-Z][A-Z_]*_\d+>'
)

# A DAX string literal: double-quoted, with "" as the escaped quote.
_DAX_STRING_LITERAL = re.compile(r'"(?:[^"]|"")*"')


def rewrite_alias_literals(dax_query: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Rewrite known alias literals in a DAX query back to their real values.

    The AI only ever sees aliases, so a follow-up filter like
    'Companies'[company_name] = "Client_A" would silently match 0 rows in the
    real tenant. This rewrites aliases back to real values, but ONLY inside
    double-quoted string literals: bare identifiers, table and column names
    are never touched. Aliases not present in the mapping stay untouched.

    Returns (rewritten_query, number_of_aliases_replaced).
    """
    count = 0

    def _replace_literal(literal_match: re.Match) -> str:
        nonlocal count
        inner = literal_match.group(0)[1:-1]

        def _replace_alias(alias_match: re.Match) -> str:
            nonlocal count
            real = mapping.get(alias_match.group(0))
            if real is None:
                return alias_match.group(0)
            count += 1
            return real.replace('"', '""')

        return '"' + _DAX_ALIAS.sub(_replace_alias, inner) + '"'

    return _DAX_STRING_LITERAL.sub(_replace_literal, dax_query), count


class Anonymizer:
    def __init__(
        self,
        registry: EntityRegistry,
        presidio_enabled: bool = True,
        enabled: bool = True,
        presidio_entities: Optional[list[str]] = None,
    ):
        self._registry = registry
        self._presidio_enabled = presidio_enabled
        self._enabled = enabled
        # Entity types Pass 2 acts on. None -> the default set (excludes
        # DATE_TIME). An explicit list from config overrides it verbatim.
        self._presidio_entities = frozenset(
            _DEFAULT_PRESIDIO_ENTITIES if presidio_entities is None
            else presidio_entities)
        self._presidio_mapping: dict[str, str] = {}   # alias -> real value
        self._presidio_counter: dict[str, int] = {}    # entity_type -> counter
        self._analyzer = None
        self._anonymizer_engine = None
        self._presidio_available: Optional[bool] = None  # None = not checked yet
        self._presidio_error: Optional[str] = None       # runtime failure message

    # ------------------------------------------------------------------
    # Presidio availability
    # ------------------------------------------------------------------

    @property
    def presidio_available(self) -> bool:
        """True if the Presidio packages can be imported. Checked once, cached."""
        if self._presidio_available is None:
            try:
                import presidio_analyzer  # noqa: F401
                import presidio_anonymizer  # noqa: F401
                self._presidio_available = True
            except ImportError:
                self._presidio_available = False
        return self._presidio_available

    def presidio_state(self) -> str:
        """One of: 'active', 'disabled', 'not_installed', 'failed'."""
        if not self._enabled or not self._presidio_enabled:
            return "disabled"
        if not self.presidio_available:
            return "not_installed"
        if self._presidio_error:
            return "failed"
        return "active"

    def presidio_status_line(self) -> str:
        """Human-readable Pass 2 status for the anonymization_status tool."""
        state = self.presidio_state()
        if state == "active":
            return "Pass 2 (Presidio): ACTIVE"
        if state == "disabled":
            return "Pass 2 (Presidio): INACTIVE (disabled in config)"
        if state == "failed":
            return f"Pass 2 (Presidio): INACTIVE (failed to start: {self._presidio_error})"
        return (
            "Pass 2 (Presidio): INACTIVE (packages not installed; "
            f"run: {PRESIDIO_INSTALL_HINT})"
        )

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
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            })
            nlp_engine = provider.create_engine()
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self._anonymizer_engine = AnonymizerEngine()
        return self._analyzer, self._anonymizer_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anonymize_text(self, text: str) -> str:
        """Two-pass anonymization on a text string."""
        if not self._enabled or not text or not isinstance(text, str):
            return text

        # Pass 1: deterministic replacement via EntityRegistry
        result = self._registry.anonymize_text(text)

        # Pass 2: Presidio NLP safety net (only when the packages are installed;
        # _init_anonymizer warns on stderr when they are not)
        if self._presidio_enabled and self.presidio_available:
            result = self._presidio_pass(result)

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

    def deanonymize_dax(self, dax_query: str) -> tuple[str, int]:
        """Rewrite alias literals in an inbound DAX query back to real values.

        Returns (rewritten_query, number_of_aliases_replaced).
        """
        if not self._enabled or not dax_query:
            return dax_query, 0
        return rewrite_alias_literals(dax_query, self.get_full_mapping())

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
        """Run Presidio NER and replace detections with indexed tokens.

        Only called when the packages are importable (see anonymize_text), so
        an exception here means a working install failed at runtime (e.g. the
        spaCy model is missing). That stays non-fatal, but is recorded and
        warned about once so it cannot fail silently.
        """
        try:
            analyzer, _ = self._get_presidio()
            results = analyzer.analyze(text=text, language="en", score_threshold=0.7)
        except Exception as e:
            if self._presidio_error is None:
                self._presidio_error = str(e)
                print(
                    f"[ANON WARNING] Pass 2 (Presidio) failed to run: {e}. "
                    "Continuing with Pass 1 only. If the spaCy model is missing, "
                    "run: python -m spacy download en_core_web_sm",
                    file=sys.stderr,
                    flush=True,
                )
            return text
        if not results:
            return text

        # Sort by start position descending so replacements don't shift offsets
        results = sorted(results, key=lambda r: r.start, reverse=True)

        for detection in results:
            original = text[detection.start:detection.end]

            # Only act on the configured entity types (DATE_TIME excluded by
            # default so dates stay readable for data-end discovery).
            if detection.entity_type not in self._presidio_entities:
                continue

            # Skip values already replaced by Pass 1
            if self._is_already_aliased(original):
                continue

            # Skip clear non-PII: allowlist, GUIDs, pure numbers/dates, DAX
            # keywords, and shape-matched categorical labels.
            if _is_presidio_false_positive(original, detection.entity_type):
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
