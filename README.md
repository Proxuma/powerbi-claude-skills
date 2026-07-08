# Proxuma Power BI Skills

AI prompt files and MCP server for generating reports and dashboards from your Power BI data. Works with Claude Code, GitHub Copilot, Cursor, and any MCP-compatible AI tool.

You ask a business question. The AI queries your data model, anonymizes it, and generates a complete HTML report or dashboard builder with real numbers. Your data never reaches the AI in readable form.

## What's included

| Component | Description |
|-----------|-------------|
| **MCP Server** | Python server connecting AI tools to Power BI and Fabric APIs |
| **Report Prompt** | Generates standalone HTML reports with KPIs, tables, analysis, and findings |
| **QBR Prompt** | Generates a board-ready Quarterly Business Review (the "Clear Perspective" design) with a PDF export button — matches your brand automatically if you point it at your website |
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
claude mcp add powerbi -- python -m server.server
```

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

The QBR prompt builds on `templates/qbr-template.html` — a self-contained, print-ready design
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

All data is automatically anonymized before it reaches the AI. The AI only sees aliases like Client_A, Resource_1, Contact_3.

### How it works

1. **On first query**, the server loads unique values from your configured sensitive columns via DAX
2. **Every response** passes through two layers:
   - **Pass 1 (deterministic lookup):** known entities get consistent aliases (fast, auditable)
   - **Pass 2 (Presidio NLP):** catches unexpected PII in free-text fields. This pass is optional and OFF by default: `pip install -r requirements.txt` does not install it, so on a default install only Pass 1 runs. To turn Pass 2 on, install the packages and the spaCy model:

     ```bash
     pip install presidio-analyzer presidio-anonymizer spacy
     python -m spacy download en_core_web_sm
     ```

     The server warns on startup when Pass 2 is configured but not installed, and the `anonymization_status` tool shows whether Pass 2 is ACTIVE or INACTIVE.
3. **After report generation**, restore real names locally

### Restoring real names

**Option A — In the browser:** Open the generated report. A yellow restore bar sits at the top of the page. Drag `~/.powerbi-mcp/sessions/latest/mapping.json` onto that bar, or click "Load mapping.json" on the bar and pick the file.

**Option B — CLI:**
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
    "presidio_enabled": true
  }
}
```

### Audit trail

Every session stores its mapping at `~/.powerbi-mcp/sessions/<id>/mapping.json`. This file never leaves your machine. Use it to verify what was anonymized and provide compliance documentation.

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
4. Subsequent runs refresh automatically — no re-login needed

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

## License

MIT
