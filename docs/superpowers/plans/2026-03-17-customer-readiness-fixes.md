# Customer Readiness Fixes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 issues in the `powerbi-claude-skills` repo so it's safe and accurate for customer use on their own Power BI data.

**Architecture:** Three blockers (Presidio over-anonymization, workspace name leaks, schema description leaks) and three polish items (token encryption, font inconsistency, tool name inconsistency). Each fix is isolated with its own tests.

**Tech Stack:** Python 3.10+, pytest, Presidio (optional), Azure Identity SDK

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `server/anonymizer.py` | Modify | Add allowlist to Presidio pass, raise score threshold |
| `server/server.py` | Modify | Anonymize workspace/dataset names and schema descriptions |
| `server/auth.py` | Modify | Default to encrypted storage with env var fallback |
| `prompts/powerbireport.md` | Modify | Fix font references (Inter → Open Sans), tool name prefix |
| `prompts/powerbi.md` | Modify | Standardize tool name references |
| `tests/test_anonymizer.py` | Modify | Add tests for allowlist, workspace anonymization |
| `tests/test_server_anonymization.py` | Create | Integration tests for server-level anonymization |

---

## Chunk 1: Presidio Over-Anonymization Fix

### Task 1: Add Presidio Allowlist to Anonymizer

The Presidio NLP safety net (Pass 2) is too aggressive. It replaces non-PII values like month names ("March" → `<DATE_TIME_1>`), Dutch priority names ("Kritiek" → `<ORGANIZATION_1>`), and common business terms. Fix: add a hardcoded allowlist of known non-PII patterns and raise the score threshold.

**Files:**
- Modify: `server/anonymizer.py:98-132` (the `_presidio_pass` method)
- Modify: `tests/test_anonymizer.py`

- [ ] **Step 1: Write failing tests for the allowlist**

Add these tests to `tests/test_anonymizer.py`:

```python
@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_month_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    for month in months:
        result = anon.anonymize_text(f"Tickets created in {month} 2026")
        assert month in result, f"{month} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_priority_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    priorities = ["Critical", "High", "Medium", "Low", "Kritiek", "Hoog", "Gemiddeld", "Laag"]
    for priority in priorities:
        result = anon.anonymize_text(f"Priority: {priority}")
        assert priority in result, f"{priority} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_does_not_anonymize_day_names():
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in days:
        result = anon.anonymize_text(f"Created on {day}")
        assert day in result, f"{day} was incorrectly anonymized to: {result}"


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_still_catches_real_pii():
    """Ensure the allowlist doesn't break real PII detection."""
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    result = anon.anonymize_text("Email john.smith@company.com about the March report")
    assert "john.smith@company.com" not in result
    assert "March" in result


@pytest.mark.skipif(not HAS_PRESIDIO, reason="presidio not installed")
def test_presidio_still_catches_standalone_person_name():
    """Person names without email context should still be caught.

    If this fails at threshold 0.7, lower to 0.6 and add more allowlist
    entries instead. Presidio scores person names 0.5-0.85 depending on context.
    """
    registry = _make_registry({})
    anon = Anonymizer(registry=registry, presidio_enabled=True)
    result = anon.anonymize_text("The ticket was assigned to John Smith for resolution")
    assert "John Smith" not in result
```

**Note:** If `test_presidio_still_catches_standalone_person_name` fails at threshold 0.7, lower `score_threshold` to 0.6 in `anonymizer.py` and re-run. The allowlist provides the primary protection against false positives now, so a lower threshold is acceptable.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/test_anonymizer.py -v -k "month or priority or day_names or still_catches"`
Expected: FAIL — month names and priority names get anonymized by Presidio

- [ ] **Step 3: Add allowlist and raise threshold in anonymizer.py**

Edit `server/anonymizer.py`. Add the allowlist constant before the class definition, and modify `_presidio_pass`:

```python
# Non-PII values that Presidio incorrectly flags.
# Months, days, priority levels (EN + NL), status names, common business terms.
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
}
```

Then modify `_presidio_pass` (lines 98-132) — raise threshold from 0.4 to 0.7 and add allowlist check:

```python
def _presidio_pass(self, text: str) -> str:
    """Run Presidio NER and replace detections with indexed tokens."""
    try:
        analyzer, _ = self._get_presidio()
    except Exception:
        return text

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/test_anonymizer.py -v`
Expected: ALL tests pass, including the 4 new ones and all 6 existing ones

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git add server/anonymizer.py tests/test_anonymizer.py
git commit -m "fix: add Presidio allowlist and raise threshold to prevent false positives

Month names, day names, Dutch/English priority levels, and common business
terms were being incorrectly anonymized by the Presidio NLP safety net.
Added an allowlist of known non-PII values and raised score_threshold
from 0.4 to 0.7 to reduce false positives while still catching real PII."
```

---

## Chunk 2: Workspace and Schema Name Leaks

### Task 2: Anonymize Workspace and Dataset Names in Server Output

`list_workspaces` and `list_datasets` return real workspace/dataset names. These often contain company names (e.g., "Contoso Production BI"). The anonymizer runs on the full output string, but workspace/dataset names aren't in the entity registry because they're not loaded from `sensitive_columns`. Fix: add workspace/dataset names to the registry dynamically when they're first seen.

**Files:**
- Modify: `server/server.py:312-342` (list_workspaces + list_datasets handlers)
- Create: `tests/test_server_anonymization.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_server_anonymization.py`:

```python
"""Tests for server-level output anonymization."""
from server.anonymizer import Anonymizer
from server.entity_registry import EntityRegistry


def _make_anonymizer(mapping: dict[str, str]) -> Anonymizer:
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    for real_val, alias in mapping.items():
        norm = real_val.strip().lower()
        registry._forward[norm] = alias
        registry._reverse[alias] = real_val
    registry._sorted_entities = sorted(
        [(n, registry._reverse[a]) for n, a in registry._forward.items()],
        key=lambda x: len(x[1]),
        reverse=True,
    )
    return Anonymizer(registry=registry, presidio_enabled=False)


def test_workspace_names_should_be_anonymizable():
    """Workspace names containing company names should be anonymized."""
    anon = _make_anonymizer({"Contoso": "Client_A"})
    output = "Available workspaces:\n\n- Contoso Production BI\n  ID: abc-123\n\n"
    result = anon.anonymize_text(output)
    assert "Contoso" not in result
    assert "Client_A" in result
    assert "abc-123" in result  # IDs should NOT be anonymized


def test_dataset_configured_by_anonymized():
    """The 'configuredBy' field often contains a person's email/name."""
    anon = _make_anonymizer({"jan.devries@company.com": "Resource_1"})
    output = "- My Dataset\n  ID: xyz-789\n  Configured by: jan.devries@company.com\n\n"
    result = anon.anonymize_text(output)
    assert "jan.devries@company.com" not in result
```

- [ ] **Step 2: Run test to verify it passes (these should already pass)**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/test_server_anonymization.py -v`
Expected: PASS — the `_anonymize_text()` call in the server handlers already runs registry replacement on the full output string. If the company name is in the registry, it gets replaced.

**Note:** The real gap is that workspace/dataset names are NOT in the entity registry by default — they're only loaded from `sensitive_columns` config. The registry needs the user to configure `sensitive_columns` to include company names. This is actually working as designed: the user configures which columns contain PII, and those values get loaded. Workspace names that happen to contain a registered company name will be caught. For names NOT in the registry, Presidio Pass 2 is the safety net.

The actual fix needed here is making sure `search_schema` output is also anonymized, which it already is (line 465 calls `_anonymize_text`). Let me verify the `configuredBy` field is handled.

- [ ] **Step 3: Verify search_schema anonymization covers descriptions**

Read `server/server.py:418-465` — the `search_schema` handler fetches decoded TMDL schema content and returns matching lines. Line 465: `return [TextContent(type="text", text=_anonymize_text(output))]`. This already anonymizes the schema output through both passes.

The TMDL schema content contains table definitions, column definitions with descriptions, and measure definitions. Any company names in descriptions will be caught by:
- Pass 1 if the company is in `sensitive_columns`
- Pass 2 (Presidio) for names not in the registry

**This is already handled.** The real issue is that `list_workspaces` returns workspace names that might not be in the entity registry. Since we can't pre-load workspace names (they're not DAX columns), the best fix is to add a `workspace_aliases` config option OR rely on Presidio to catch company names in workspace titles.

Since we raised Presidio threshold to 0.7 in Task 1, we should add workspace/dataset name anonymization as a separate pass. Let me revise:

- [ ] **Step 4: Add dynamic workspace name registration**

Edit `server/server.py` — after the `list_workspaces` API call, register workspace names in the entity registry before anonymizing:

In the `list_workspaces` handler (around line 318), add workspace name registration:

```python
        if name == "list_workspaces":
            response = requests.get(
                "https://api.powerbi.com/v1.0/myorg/groups",
                headers=get_powerbi_headers()
            )
            response.raise_for_status()
            data = response.json()
            workspaces = data.get("value", [])

            # Register workspace names for anonymization
            # NOTE: server.py:499 has a pre-existing bug: `anon.enabled` (no underscore).
            # The attribute is `_enabled`. Fix line 499 to `anon._enabled` while here.
            anon = _init_anonymizer()
            if anon._enabled:
                for i, ws in enumerate(workspaces):
                    ws_name = ws.get("name", "")
                    if ws_name:
                        anon._registry.register_dynamic(
                            ws_name, "workspace", i
                        )

            output = "Available workspaces:\n\n"
            for ws in workspaces:
                output += f"- {ws.get('name', 'Unknown')}\n  ID: {ws.get('id')}\n\n"
            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]
```

Do the same for `list_datasets` (around line 339) — register dataset names and `configuredBy` values:

```python
            # Register dataset names and configuredBy for anonymization
            anon = _init_anonymizer()
            if anon._enabled:
                for i, ds in enumerate(datasets):
                    ds_name = ds.get("name", "")
                    if ds_name:
                        anon._registry.register_dynamic(
                            ds_name, "dataset", i
                        )
                    configured_by = ds.get("configuredBy", "")
                    if configured_by:
                        anon._registry.register_dynamic(
                            configured_by, "contact", None
                        )
```

- [ ] **Step 5: Add `register_dynamic` method to EntityRegistry**

Edit `server/entity_registry.py` — add a method that registers a value at runtime (not from DAX):

```python
def register_dynamic(self, value: str, category: str, index: int = None):
    """Register a value for anonymization at runtime (not from DAX columns).

    Used for workspace names, dataset names, and other values discovered
    during tool execution that aren't in the pre-loaded sensitive columns.
    """
    norm = _normalize(value)  # module-level function, NOT self._normalize
    if norm in self._forward:
        return  # Already registered

    if index is None:
        # Auto-increment: find the next available index for this category
        index = 0
        while True:
            alias = _default_alias(category, index)  # existing module-level function
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
```

**Important:** `_normalize()` and `_default_alias()` are module-level functions in `entity_registry.py` (lines 13 and 26), NOT methods on the class. Do NOT prefix them with `self.`.

- [ ] **Step 6: Add test for dynamic registration**

Add to `tests/test_server_anonymization.py`:

```python
def test_register_dynamic_workspace():
    """Dynamic registration should anonymize workspace names."""
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    registry.register_dynamic("Contoso Production BI", "workspace", 0)
    anon = Anonymizer(registry=registry, presidio_enabled=False)
    output = "- Contoso Production BI\n  ID: abc-123"
    result = anon.anonymize_text(output)
    assert "Contoso Production BI" not in result
    assert "Workspace_1" in result  # _default_alias fallback: "Workspace_{index+1}"
    assert "abc-123" in result


def test_register_dynamic_auto_index():
    """Auto-index should pick the next available index."""
    registry = EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {})
    registry.register_dynamic("jan@company.com", "contact")
    registry.register_dynamic("piet@company.com", "contact")
    assert "Contact_1" in registry._reverse
    assert "Contact_2" in registry._reverse
```

- [ ] **Step 7: Run all tests**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/ -v`
Expected: ALL tests pass

- [ ] **Step 8: Commit**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git add server/server.py server/entity_registry.py tests/test_server_anonymization.py
git commit -m "fix: anonymize workspace/dataset names and configuredBy values

Workspace and dataset names often contain company names that weren't
being anonymized because they're not loaded from sensitive_columns.
Added register_dynamic() to EntityRegistry for runtime registration,
and the list_workspaces/list_datasets handlers now register names
before anonymizing the output."
```

---

## Chunk 3: Auth Token Encryption Default

### Task 3: Default to Encrypted Token Storage

`allow_unencrypted_storage=True` means tokens are stored in plaintext in `~/.powerbi-mcp/`. For customer use, default to encrypted with a fallback env var.

**Files:**
- Modify: `server/auth.py:43-46`
- Modify: `server/config.example.json`

- [ ] **Step 1: Add `import os` to auth.py**

Edit `server/auth.py` line 2 — add `import os` after `import json`:

```python
import json
import os
import time
```

- [ ] **Step 2: Modify auth.py to default to encrypted**

Edit `server/auth.py` lines 43-46 — replace the `cache_options` block:

```python
    # Default to encrypted storage. Set POWERBI_MCP_ALLOW_UNENCRYPTED=1
    # if your OS doesn't support encrypted credential storage (e.g., some
    # Linux distros without a keyring, or headless Docker containers).
    allow_unencrypted = os.environ.get("POWERBI_MCP_ALLOW_UNENCRYPTED", "0") == "1"
    cache_options = TokenCachePersistenceOptions(
        name="powerbi-mcp",
        allow_unencrypted_storage=allow_unencrypted
    )
```

- [ ] **Step 3: Update config.example.json**

Add a comment about the env var in the example config. Since JSON doesn't support comments, add it to a `_notes` field or document it in the README section instead. Actually, just make sure the README documents this. For now, this is sufficient.

- [ ] **Step 4: Run existing tests to verify no breakage**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/ -v`
Expected: ALL tests pass (auth module isn't tested directly, but import-level issues would surface)

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git add server/auth.py
git commit -m "security: default to encrypted token storage

Changed allow_unencrypted_storage from True to False. Customers on
systems without a keyring can set POWERBI_MCP_ALLOW_UNENCRYPTED=1
to fall back to plaintext storage."
```

---

## Chunk 4: Font and Tool Name Consistency

### Task 4: Fix Font Reference in powerbireport.md

The prompt references `Inter` as the body font, but the template (`report-shell.html`) uses `Open Sans`. The template is the source of truth.

**Files:**
- Modify: `prompts/powerbireport.md:61` (font link)

- [ ] **Step 1: Replace Inter with Open Sans in the Google Fonts link**

Edit `prompts/powerbireport.md` line 61 — change the font link:

Old:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

New:
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Open+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Update any CSS references to Inter in the prompt**

Search `prompts/powerbireport.md` for `Inter` and replace with `'Open Sans'` in any `font-family` declarations. Also update the design tokens section if it mentions "Body font: Inter" to say "Body font: Open Sans".

- [ ] **Step 3: Commit**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git add prompts/powerbireport.md
git commit -m "fix: align font references with template (Inter → Open Sans)"
```

### Task 5: Standardize Tool Name References

`powerbi.md` uses `mcp__powerbi__execute_dax()` format, `powerbireport.md` uses bare `execute_dax()`. Standardize to bare names (since the MCP prefix is added automatically by the client).

**Files:**
- Modify: `prompts/powerbi.md:18-19, 38-42, 52-54`

- [ ] **Step 1: Replace mcp__powerbi__ prefix with bare tool names**

Edit `prompts/powerbi.md` — replace all `mcp__powerbi__` prefixes with bare names:

- `mcp__powerbi__list_workspaces()` → `list_workspaces()`
- `mcp__powerbi__list_datasets(...)` → `list_datasets(...)`
- `mcp__powerbi__search_schema(...)` → `search_schema(...)`
- `mcp__powerbi__execute_dax(...)` → `execute_dax(...)`

- [ ] **Step 2: Commit**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git add prompts/powerbi.md
git commit -m "fix: standardize tool names to bare format across all prompts"
```

---

## Chunk 5: Final Verification

### Task 6: Run Full Test Suite and Verify

- [ ] **Step 1: Run all tests**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && python -m pytest tests/ -v --tb=short`
Expected: ALL tests pass

- [ ] **Step 2: Verify font consistency across files**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && grep -rn "Inter" prompts/ templates/`
Expected: No references to `Inter` as a font family (only in words like "Internal" or "interface" which are fine)

- [ ] **Step 3: Verify tool name consistency**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && grep -rn "mcp__powerbi__" prompts/`
Expected: No results — all prompts should use bare tool names

- [ ] **Step 4: Verify no unencrypted default**

Run: `cd ~/ClaudeCode/powerbi-claude-skills && grep -n "allow_unencrypted" server/auth.py`
Expected: Shows the env var check, NOT `True`

- [ ] **Step 5: Push to GitHub**

```bash
cd ~/ClaudeCode/powerbi-claude-skills
git push origin main
```
