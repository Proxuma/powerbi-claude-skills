"""Deterministic entity anonymization registry.

Loads unique values from Power BI dimension tables and builds a
bidirectional mapping (real value <-> alias). The mapping is consistent
within a session: same input always produces the same alias.
"""

import random
import re
import time
import unicodedata
from typing import Callable, Optional

# Power BI answers a bulk load with HTTP 429 and a message carrying its own
# cooldown ("Retry in 60 seconds."). Honour that hint when present - guessing a
# shorter backoff just burns another attempt against the same limit.
_RATE_LIMIT_MARKERS = ("429", "exceeded the amount of requests", "too many requests")
_RETRY_HINT = re.compile(r"retry in (\d+) seconds?", re.I)


def _is_registrable(value: str) -> bool:
    """Reject values that cannot be a real entity name but wreck output.

    A contact row holding "-" or "." registers that character as an entity, and
    anonymize_text then rewrites every hyphen in the response: the date
    "2025-09" comes back as "2025Contact_46053" and every ISO date, phone
    number and age bucket in the report turns to noise.

    A real client, resource or contact name always contains at least one letter
    and is longer than a single character.
    """
    stripped = value.strip()
    if len(stripped) < 2:
        return False
    return any(ch.isalpha() for ch in stripped)


def _is_rate_limited(err: Exception) -> bool:
    msg = str(err).lower()
    return any(m in msg for m in _RATE_LIMIT_MARKERS)


def _retry_after(err: Exception) -> Optional[float]:
    match = _RETRY_HINT.search(str(err))
    return float(match.group(1)) if match else None


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


# Generic values that routinely sit in contact/resource columns as service or
# system accounts ("Admin", "User", "API"). Registering them is actively harmful:
# anonymize_text replaces a registered value wherever it appears as a whole word,
# so a contact literally named "Desk" rewrites the role "Help Desk" into
# "Help Contact_48182" and the output becomes unreadable.
#
# This matches WHOLE registered values only, never substrings, so a real company
# named "Support B.V." is still masked - its registered value is "Support B.V.",
# which is not in this set. The cost is precise and bounded: an entity whose
# entire name is one of these words is not masked by Pass 1.
_DEFAULT_NEVER_MASK = frozenset({
    "admin", "administrator", "administratie", "api", "beheer", "default",
    "desk", "guest", "helpdesk", "info", "mail", "email", "n/a", "na", "none",
    "noreply", "no-reply", "onbekend", "root", "service", "servicedesk",
    "support", "system", "systeem", "test", "unknown", "user", "users",
})


class EntityRegistry:
    def __init__(
        self,
        sensitive_columns: dict[str, list[str]],
        dax_executor: Callable[[str], dict],
        never_mask: Optional[list[str]] = None,
        use_default_never_mask: bool = True,
        max_retries: int = 4,
        retry_base_delay: float = 2.0,
        request_delay: float = 0.0,
        fail_on_degraded: bool = True,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Initialize the registry.

        Args:
            sensitive_columns: Mapping of category to list of DAX column
                references, e.g. {"client": ["'Table'[Col]"]}.
            dax_executor: Function that takes a DAX query string and
                returns the JSON response from Power BI.
            never_mask: Extra whole values to keep out of the registry, on top
                of the built-in defaults. Compared case-insensitively against
                the entire value, never against substrings.
            use_default_never_mask: Set False to drop the built-in generic
                terms and rely only on never_mask.
            max_retries: Attempts per column when Power BI rate-limits the
                bulk load. Non-rate-limit errors are not retried.
            retry_base_delay: Seconds for the first backoff step; doubles each
                attempt, with jitter. A "Retry in N seconds" hint from Power BI
                overrides it.
            request_delay: Seconds to pace between column fetches. Loading many
                columns back to back is what trips the limit in the first place.
            fail_on_degraded: Raise if any column still fails after retries.
                Defaults True: a column that failed to load is a column whose
                values are NOT masked, so serving on regardless leaks silently.
            sleep: Injected for tests.
        """
        self._sensitive_columns = sensitive_columns
        self._dax_executor = dax_executor
        self._never_mask = {
            _normalize(v) for v in (never_mask or []) if v and v.strip()
        }
        if use_default_never_mask:
            self._never_mask |= _DEFAULT_NEVER_MASK
        self._skipped: set[str] = set()
        self._max_retries = max(1, max_retries)
        self._retry_base_delay = retry_base_delay
        self._request_delay = request_delay
        self._fail_on_degraded = fail_on_degraded
        self._sleep = sleep
        self.failed_columns: list[str] = []
        self._forward: dict[str, str] = {}  # normalized_real_value -> alias
        self._reverse: dict[str, str] = {}  # alias -> original_real_value
        self._sorted_entities: list[tuple[str, str]] = []  # for longest-match-first
        self.is_degraded = False
        self._warnings: list[str] = []

    def initialize(self):
        """Query all sensitive columns and build the mapping."""
        first_fetch = True
        for category, columns in self._sensitive_columns.items():
            counter = 0
            for col_ref in columns:
                try:
                    if self._request_delay and not first_fetch:
                        self._sleep(self._request_delay)
                    first_fetch = False
                    values = self._fetch_with_retry(col_ref)
                    for val in values:
                        norm = _normalize(val)
                        if not _is_registrable(val):
                            continue
                        if norm in self._never_mask:
                            self._skipped.add(val)
                            continue
                        if norm and norm not in self._forward:
                            alias = _default_alias(category, counter)
                            self._forward[norm] = alias
                            self._reverse[alias] = val
                            counter += 1
                except Exception as e:
                    self._warnings.append(f"Failed to load {col_ref}: {e}")
                    self.failed_columns.append(col_ref)
                    self.is_degraded = True

        if self.is_degraded and self._fail_on_degraded:
            raise RuntimeError(
                f"Anonymization registry incomplete: {len(self.failed_columns)} "
                f"column(s) failed to load after {self._max_retries} attempt(s). "
                f"Their values would reach the AI unmasked, so startup is refused. "
                f"Columns: {', '.join(self.failed_columns)}. "
                f"Set anonymization.fail_on_degraded=false to serve anyway."
            )

        # Sort by length descending for longest-match-first replacement
        self._sorted_entities = sorted(
            [
                (norm, self._reverse[alias])
                for norm, alias in self._forward.items()
            ],
            key=lambda x: len(x[1]),
            reverse=True,
        )

    def _fetch_with_retry(self, col_ref: str) -> list[str]:
        """Fetch one column, retrying while Power BI reports a rate limit.

        Only rate-limit errors are retried: a missing column or a malformed
        reference fails the same way on every attempt, and retrying it just
        delays a real error behind several minutes of backoff.
        """
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._fetch_distinct_values(col_ref)
            except Exception as e:
                last_error = e
                if not _is_rate_limited(e) or attempt == self._max_retries - 1:
                    raise
                hint = _retry_after(e)
                if hint is None:
                    hint = self._retry_base_delay * (2 ** attempt)
                # Jitter so a burst of columns does not retry in lockstep.
                self._sleep(hint + random.uniform(0, 1))
        raise last_error  # unreachable; keeps type checkers honest

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
            # Boundary guards: a client named "IT" or "May" must not rewrite
            # those letters inside "quality" or "Maybe". Conditional lookarounds
            # because entity values can start or end with punctuation, where a
            # plain \b never matches.
            prefix = r"(?<!\w)" if re.match(r"\w", original) else ""
            suffix = r"(?!\w)" if re.search(r"\w$", original) else ""
            pattern = re.compile(prefix + re.escape(original) + suffix, re.IGNORECASE)
            result = pattern.sub(alias, result)
        return result

    def get_mapping(self) -> dict[str, str]:
        """Return alias -> real_value mapping."""
        return dict(self._reverse)

    def get_skipped(self) -> list[str]:
        """Values held out of the registry by the never-mask list.

        These reach the AI in the clear. Surfaced so the exemption is auditable
        rather than silent - see anonymization_status.
        """
        return sorted(self._skipped)

    def register_dynamic(self, value: str, category: str, index: int = None):
        """Register a value for anonymization at runtime (not from DAX columns).

        Used for workspace names, dataset names, and other values discovered
        during tool execution that aren't in the pre-loaded sensitive columns.
        """
        norm = _normalize(value)
        if norm in self._forward:
            return  # Already registered

        if index is None:
            # Auto-increment: find the next available index for this category
            index = 0
            while True:
                alias = _default_alias(category, index)
                if alias not in self._reverse:
                    break
                index += 1

        alias = _default_alias(category, index)
        self._forward[norm] = alias
        self._reverse[alias] = value

        # Rebuild sorted entities for longest-match-first
        self._sorted_entities = sorted(
            [(n, self._reverse[a]) for n, a in self._forward.items()],
            key=lambda x: len(x[1]),
            reverse=True,
        )

    def get_warnings(self) -> list[str]:
        """Return list of warnings encountered during initialization."""
        return list(self._warnings)
