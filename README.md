# Proxuma Power BI Skills

AI prompt files and MCP server for generating reports and dashboards from your Power BI data. Works with Claude Code, GitHub Copilot, Cursor, and any MCP-compatible AI tool.

You ask a business question. The AI queries your data model, anonymizes it, and generates a complete HTML report or dashboard builder with real numbers. Your data never reaches the AI in readable form.

## What's included

| Component | Description |
|-----------|-------------|
| **MCP Server** | Python server connecting AI tools to Power BI and Fabric APIs |
| **Report Prompt** | Generates standalone HTML reports with KPIs, tables, analysis, and findings |
| **QBR Prompt** | Generates Quarterly Business Review reports |
| **Dashboard Prompt** | Generates interactive dashboard mockups with Power BI build instructions |
| **Project Report Prompt** | Generates project status reports |
| **Data Anonymization** | Two-pass anonymization: deterministic aliases + NLP safety net |
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
| `prompts/powerbireportQBR.md` | `#powerbireportQBR Q1 2026` |
| `prompts/powerbidashboard.md` | `#powerbidashboard SLA performance` |
| `prompts/projectreport.md` | `#projectreport Project Alpha` |
| `prompts/powerbi.md` | General Power BI data questions |

## Data anonymization

All data is automatically anonymized before it reaches the AI. The AI only sees aliases like Client_A, Resource_1, Contact_3.

### How it works

1. **On first query**, the server loads unique values from your configured sensitive columns via DAX
2. **Every response** passes through two layers:
   - **Pass 1** — Deterministic lookup: known entities get consistent aliases (fast, auditable)
   - **Pass 2** — Presidio NLP: catches unexpected PII in free-text fields (optional safety net)
3. **After report generation**, restore real names locally

### Restoring real names

**Option A — Drag and drop:** Open the generated report in a browser. Drag `~/.powerbi-mcp/sessions/latest/mapping.json` onto the restore button at the top of the page.

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
│   ├── powerbidashboard.md    # Dashboard builder
│   ├── projectreport.md       # Project report generator
│   └── powerbi.md             # General Power BI queries
├── templates/
│   └── report-shell.html      # Report HTML template (with restore UI)
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
