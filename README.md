# Proxuma Power BI Skills

Ask your Power BI data a question in plain language, get back a complete standalone HTML report with real numbers. Prompt files plus an MCP server that connect your own AI assistant to your Power BI and Fabric data. Works with Claude Code, GitHub Copilot, Cursor, and any MCP-compatible AI tool.

Built for MSPs on the Proxuma Power BI product who want to query their own tenant with their own AI. You ask a business question. The AI queries your data model, anonymizes it, and builds the report from real figures. Client names, staff, and contacts are swapped for aliases before anything leaves for the AI, so your data never reaches the AI in readable form.

## What's included

| Component | Description |
|-----------|-------------|
| **MCP Server** | Python server connecting AI tools to Power BI and Fabric APIs |
| **Report Prompt** | Generates standalone HTML reports with KPIs, tables, analysis, and findings |
| **QBR Prompt** | Generates a board-ready Quarterly Business Review (the "Clear Perspective" design) with a PDF export button. Matches your brand automatically if you point it at your website |
| **Project Report Prompt** | Generates project status reports |
| **Data Anonymization** | Two-pass anonymization: deterministic aliases + NLP safety net |
| **DAX Verifier** | Re-runs every DAX query in a generated report and checks that the numbers match your data |
| **Setup Wizard** | Auto-discovers workspaces, datasets, and sensitive columns |

## Quick start

```bash
git clone https://github.com/Proxuma/powerbi-claude-skills.git
cd powerbi-claude-skills
pip install -r requirements.txt
python -m server.wizard
```

The wizard walks you through Microsoft sign-in, picks your workspace and dataset, detects sensitive columns, and writes the config. No GUIDs to hunt for.

Then add the MCP server to your AI tool:

**Claude Code:**
```bash
claude mcp add powerbi -- bash -c "cd /path/to/powerbi-claude-skills && exec python -m server.server"
```

The `cd` matters: the server must start from the repo directory, and with the
Python environment you installed the requirements into. If you used a venv,
point at `.venv/bin/python` instead of `python`.

**VS Code (GitHub Copilot / Cursor):**
Add to `.vscode/mcp.json`:
```json
{
  "servers": {
    "powerbi": {
      "command": "python",
      "args": ["-m", "server.server"],
      "cwd": "/path/to/powerbi-claude-skills"
    }
  }
}
```

**Claude Desktop:**
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "powerbi": {
      "command": "python",
      "args": ["-m", "server.server"],
      "cwd": "/path/to/powerbi-claude-skills"
    }
  }
}
```

## Prompts

Import these as slash commands or paste them as system prompts.

| File | Use |
|------|-----|
| `prompts/powerbireport.md` | `#powerbireport what is my monthly revenue trend?` |
| `prompts/powerbireportQBR.md` | `#powerbireportQBR Contoso Q1 2026` |
| `prompts/projectreport.md` | `#projectreport Project Alpha` |
| `prompts/powerbi.md` | General Power BI data questions |

## Build your own skill

The prompts above are plain markdown files. To add your own report type (patch compliance,
onboarding status, license true-up, anything your data supports), copy an existing prompt and
keep three things intact.

**1. The anatomy.** Every skill prompt follows the same shape:

```
# Title + one-line purpose
**Input:** $ARGUMENTS            <- what the user types after the command
## Discovery                     <- find the data: search_schema + list_measures,
                                    never get_schema (it can exceed 10MB)
## Queries                       <- the DAX to run, capped with TOPN/filters
## Output                        <- exact structure of the HTML/answer
## Verification                  <- what the AI must check before claiming done
```

Start from `prompts/powerbi.md` for a question-answer skill or `prompts/powerbireport.md` for
a full HTML report. Save the file in `prompts/`, register it as a slash command in your AI
tool, done.

**2. The anonymization contract.** Include this block verbatim near the top of every new
prompt. It is the standing agreement between your skill and the MCP server:

> Data comes pre-anonymized. The MCP server anonymizes every response before it reaches you:
> you will see aliases like `Client_A`, `Resource_1`, `Contact_3`, never real names. Do not
> add, remove, or second-guess anonymization, and do not invent placeholder names yourself.
> Build the output with the aliases exactly as returned. Real names are restored locally
> afterwards by the deanonymizer; the mapping never leaves the user's machine. When you filter
> a query to one entity, filter on its numeric id, not on an aliased name.

**3. The DAX proof requirement.** Every number in the output must come from a DAX query the
AI actually ran, and each data section must embed that exact query in a collapsible panel
(`dax-toggle` in reports, `dax-proof` in QBRs; see the templates for markup). This is what
makes the output checkable: anyone can copy a query, run it against the dataset, and confirm
the numbers. It also means `tools/verify_report.py` can re-run every query in your new
skill's output automatically. A skill that produces numbers without embedded DAX is not
verifiable and does not belong in this repo.

## QBR styling and branding

The QBR prompt builds on `templates/qbr-template.html`, a self-contained, print-ready design
with a cover, a maturity benchmark, service/security/hardware/contract sections, a risk and
action list, and a floating **Export as PDF** button.

- **Say nothing about styling** and you get the default "Clear Perspective" look.
- **Point it at your website** ("match acme-it.com", "use our brand", or hand it your logo) and
  it re-skins the report to your palette and fonts and drops in your logo, calibrated so it
  reads cleanly on the header background. The layout and components stay the same; only the
  brand layer changes.
- Report prose is written in whatever language you work in (English by default); numbers format
  to the matching locale.

You never anonymize by hand for the QBR. The MCP hands the AI aliased data, the report is built
from those aliases, and real names are restored locally at the end (see below).

## Data anonymization

All data is anonymized before it reaches the AI. The AI only ever sees aliases like Client_A, Resource_1, Contact_3.

There is no second AI doing this, and nothing runs in the cloud. The anonymizer *is* the MCP server: a small Python process on your own machine, sitting between Power BI and the AI. On the way out it replaces sensitive names with codenames; on the way back it swaps the real names in. The codebook stays on your disk. Think local find-and-replace proxy, not a model. Numbers are never touched, only names, so the AI still reasons over your real figures.

### How it works

1. **On first query**, the server loads unique values from your configured sensitive columns via DAX
2. **Every response** passes through two layers:
   - **Pass 1 (deterministic lookup):** known entities get consistent aliases (fast, auditable)
   - **Pass 2 (Presidio):** an offline safety net for stray PII in free-text fields. It uses [Microsoft Presidio](https://github.com/microsoft/presidio) with a small local spaCy NER model (~12MB), not an LLM, and it makes no API call. This pass is optional and OFF by default: `pip install -r requirements.txt` does not install it, so on a default install only Pass 1 runs. To turn Pass 2 on, install the packages and the spaCy model:

     ```bash
     pip install presidio-analyzer presidio-anonymizer spacy
     python -m spacy download en_core_web_sm
     ```

     The server warns on startup when Pass 2 is configured but not installed, and the `anonymization_status` tool shows whether Pass 2 is ACTIVE or INACTIVE.

     Pass 2 masks the entity types listed in `presidio_entities` (person, organisation, email, phone, and other PII). `DATE_TIME` is deliberately **not** in the default set: masking dates turns `MAX(create_date)` into a token and stops the AI from discovering where the data ends. Pass 2 also leaves clear non-PII untouched, so GUIDs, pure numbers and ISO dates, DAX/schema identifiers (e.g. `DIVIDE`, `Hours`, `Ratio`), and priority tiers (`P1-…`) stay readable. Reducing this list only ever removes masking; add an entity type to mask more. Pass 1 (the deterministic registry) is unaffected by this setting.
3. **After report generation**, restore real names locally

The guarantee is only as strong as your sensitive-column list. Pass 1 masks the columns you flag. If a real name sits in a free-text field you did not flag and Pass 2 is off, it can reach the AI in the clear. That is what Pass 2 is for, and why the wizard auto-detects sensitive columns for you. When in doubt, flag the column or turn Pass 2 on.

### Restoring real names

**Option A, in the browser:** Open the generated report. A yellow restore bar sits at the top of the page. Drag `~/.powerbi-mcp/sessions/latest/mapping.json` onto that bar, or click "Load mapping.json" on the bar and pick the file.

**Option B, the CLI:**
```bash
python -m server report.html -o report-real.html
```

### Configuration

The wizard (option 4) auto-detects sensitive columns. Or edit `~/.powerbi-mcp/config.json` manually:

```json
{
  "anonymization": {
    "enabled": true,
    "sensitive_columns": {
      "client": ["'Company'[CompanyName]"],
      "resource": ["'Resource'[FullName]"],
      "contact": ["'Contact'[ContactName]"]
    },
    "presidio_enabled": true,
    "presidio_entities": [
      "PERSON", "ORGANIZATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION",
      "NRP", "CREDIT_CARD", "IBAN_CODE", "US_SSN", "IP_ADDRESS", "URL"
    ]
  }
}
```

`presidio_entities` is optional; omit it to use the default set. It excludes `DATE_TIME` on purpose (see above). Add or remove entity types to control what Pass 2 masks.

### Audit trail

Every session stores its mapping at `~/.powerbi-mcp/sessions/<id>/mapping.json`. This file never leaves your machine. Use it to verify what was anonymized and provide compliance documentation.

## Data protection: scope and limits

The anonymizer reduces what reaches the AI. It does not guarantee zero exposure. The protection boundary is the columns you configure plus, if installed, Presidio's name-detection categories. Identifying information that lives outside both can still reach the AI. Read this before you share a report externally.

We tested this with an adversarial run against a real model. The masker itself is correct: on the columns you configure, it does not leak. The gap is scope, not a broken masker. What follows is the verified boundary.

### What is protected

Pass 1 (the default, always on) protects every value in a column you have configured as sensitive. It catches that value in its exact form, in case variants, and in possessive form (`Acme's`), and it does so wherever the value appears in the output, even when the value sits inside a column you did not configure. The match is value-based, not column-based: a configured client name is aliased anywhere it turns up, including embedded in free text.

### What is not protected

Pass 1 does **not** protect:

- **Reformatted versions of a configured name.** If a name is line-wrapped, hyphenated, embedded as a fragment in a hostname or asset tag, or used as the local part of an email address, Pass 1 does not recognise it and it can reach the AI in the clear. Pass 1 matches the exact registered form only.
- **The own content of columns you did not configure.** A free-text column (ticket or task titles, notes, descriptions, resolutions) or a descriptive column (role, specialty, department, sector) ships its own text to the AI verbatim. On a real tenant these fields routinely carry client identifiers.

### What Presidio (Pass 2) adds

Pass 2 is an **optional extra install** (see the Data anonymization section above). It is off on a default `pip install -r requirements.txt`. When installed, it recovers most of the reformatted names Pass 1 misses using an offline name-detection model:

- line-wrapped names: roughly three quarters caught
- hyphenated names: roughly seven in eight caught
- names inside email addresses: effectively all caught
- client abbreviations embedded in hostnames or asset tags: only about four in ten caught, so most of these still leak

Pass 2 adds nothing for descriptive or sector content, because a job title or specialty is not a name. On a default install (no Presidio), only Pass 1 runs, so only the exact configured values are protected and every reformatted version of a name leaks.

### Residual risk (neither pass catches these)

1. **Indirect re-identification through descriptive columns.** A column like role or specialty (for example "Audiological scientist") is never masked, and it can reveal the client's sector even while the names beside it are aliased. This survives a full install with Presidio on.
2. **Client abbreviations inside hostnames and asset tags.** A short form of a client name embedded in a device name leaks fully on a default install and mostly even with Presidio.
3. **The own free-text content of columns you did not configure.** Ticket and task titles, notes, and project or contract codenames pass through as written. On a real tenant these carry client identifiers directly.

### What you must do

- **Configure every column that carries an identifier**, not just the obvious name columns. The configured list is the protection boundary. Anything outside it is published as written. That includes descriptive columns (role, department, sector) and free-text columns, not only company and contact names.
- **Install Presidio if your reports touch free text.** The default install does not include it. Add it with `pip install presidio-analyzer presidio-anonymizer spacy` and `python -m spacy download en_core_web_sm`, then set `presidio_enabled: true`.
- **Review a report before you share it externally.** The tool reduces exposure; it does not guarantee that nothing identifying remains. Read the anonymized output and confirm it is safe for its audience.

## MCP tools

Once the server is running, your AI assistant has access to:

| Tool | Description |
|------|-------------|
| `list_workspaces` | List all Power BI workspaces |
| `list_datasets` | List datasets in a workspace |
| `execute_dax` | Run a DAX query and get anonymized results |
| `search_schema` | Search for measures, columns, or tables |
| `list_measures` | List all measure names |
| `list_fabric_items` | List items in a Fabric workspace |
| `get_schema` | Full schema (caution: can be >10MB) |
| `anonymization_status` | Show anonymization state and entity counts |

## Verify a report's numbers

Every generated report carries the DAX query that produced each section's numbers, in a collapsible panel. You do not have to take those numbers on trust: the verifier re-runs every query against your own tenant and checks that the values in the report match what Power BI returns.

```bash
python3 tools/verify_report.py report.html
```

The tool extracts every query from the report (both the standard report's DAX toggles and the QBR's DAX proof panels), executes each one, and compares the returned values against the numbers stated in the query's `-- Result:` comment line. It prints a PASS/FAIL table per query and exits nonzero on any failure, so you can run it in a pipeline:

```
Extracted 3 DAX queries (1 dax-toggle, 2 dax-proof)

SECTION          STATUS  DETAIL
---------------  ------  ----------------------------------------
Total companies  PASS    1 value(s) match
Service desk     FAIL    expected 68000 not in returned values [67521.0]
Asset density    PASS    1 value(s) match
```

Details:

- The dataset id resolves the same way the MCP server resolves it. Pass `--dataset-id` to override.
- Queries that still contain anonymization aliases (Client_A, `<PERSON_1>`) are rewritten to real values before execution, using the session mapping and the same code path as the server's `execute_dax`. Only names are ever aliased, never numbers, so the value comparison is unaffected.
- Values match at the precision the report displays: a report that shows 4.7 passes when the model returns 4.7143. Percentages match both 93 and 0.93.
- A query without a `-- Result:` line is still executed and must run without error; its values are not checked and the table says so.
- `--extract-only` lists the queries without executing them. `--json results.json` writes a machine-readable copy.

## Requirements

- Python 3.10+
- Power BI Pro or Premium Per User license (for API access)
- An MCP-compatible AI tool (Claude Code, GitHub Copilot, Cursor, Claude Desktop)

No Azure app registration needed. The server uses the same public client flow as Power BI Desktop.

## Authentication

1. The wizard opens a browser for Microsoft sign-in
2. You sign in with your Power BI account
3. Tokens are cached locally in `~/.powerbi-mcp/`
4. Subsequent runs refresh automatically, no re-login needed

Tokens are stored only on your machine. The MCP server never sends credentials to any third party.

## Project structure

```
powerbi-claude-skills/
├── server/
│   ├── server.py              # MCP server
│   ├── auth.py                # Azure AD authentication
│   ├── wizard.py              # Setup wizard
│   ├── entity_registry.py     # Deterministic entity anonymization
│   ├── anonymizer.py          # Two-pass anonymizer (registry + Presidio)
│   ├── mapping.py             # Session mapping persistence
│   ├── deanonymizer.py        # Restore real names (XSS-safe)
│   ├── __main__.py            # CLI deanonymize entry point
│   └── config.example.json    # Example configuration
├── prompts/
│   ├── powerbireport.md       # Report generator
│   ├── powerbireportQBR.md    # QBR report generator
│   ├── projectreport.md       # Project report generator
│   └── powerbi.md             # General Power BI queries
├── templates/
│   ├── report-shell.html      # Report HTML template (with restore UI)
│   └── qbr-template.html      # QBR design template ("Clear Perspective", re-skinnable, PDF-ready)
├── tools/
│   └── verify_report.py       # Re-run a report's DAX and check its numbers
├── tests/                     # Test suite
├── requirements.txt
├── LICENSE
└── README.md
```

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Compatibility

| AI Tool | Status |
|---------|--------|
| Claude Code (CLI) | Supported |
| GitHub Copilot (VS Code, Agent mode) | Supported |
| Claude Desktop | Supported |
| Cursor | Supported |
| ChatGPT (via MCP plugin) | Experimental |

## Built by Proxuma

Built and maintained by [Proxuma](https://proxuma.io) for MSPs running Power BI. It pairs with the Proxuma Power BI product at [proxuma.io/powerbi](https://proxuma.io/powerbi).

## License

MIT
