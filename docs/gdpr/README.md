# GDPR Documentation — Power BI MCP Server

> **THIS IS NOT LEGAL ADVICE.** Consult your Data Protection Officer (DPO) or legal counsel before relying on this documentation. These templates are starting points, not final compliance artifacts.

## Processing Chain

```
MSP Client Data (Power BI)
    → Proxuma MCP Server (anonymization layer)
        → Anthropic Claude API (LLM processing)
            → Anonymized report output
                → Deanonymization (local, never leaves machine)
                    → Final report with real names
```

## Roles

| Party | GDPR Role | Responsibility |
|-------|-----------|---------------|
| MSP's Client | Data Subject | Rights holder (access, erasure, portability) |
| MSP | Data Controller | Determines purpose and means of processing |
| Proxuma | Data Processor | Provides anonymization tooling, acts on MSP instructions |
| Anthropic | Sub-Processor | LLM inference on anonymized data only |

## Anonymization Layers

1. **Layer 1 — Entity Registry**: Deterministic replacement of known entities (client names, resource names, contacts) with consistent aliases
2. **Layer 2 — Presidio NLP**: spaCy-powered NER catches PII not in the registry (free-text names, emails, phone numbers)
3. **Layer 3 — Dutch Name Detection**: Regex patterns for Dutch compound names with tussenvoegsels
4. **Layer 4 — Financial Noise** (optional): Deterministic noise on currency amounts

## Key Controls

- Mapping files stored locally only (`~/.powerbi-mcp/sessions/`), never transmitted
- Optional Fernet encryption for mapping files (S2)
- DAX result row limit (default 5,000 rows) prevents bulk data extraction
- Audit logging of all tool calls (no raw data logged)
- Rate limiting prevents runaway API usage
- Session retention with automatic cleanup (default 90 days)

## Documents in This Directory

| Document | Purpose |
|----------|---------|
| `DPIA-template.md` | Fillable Data Protection Impact Assessment for MSPs |
| `sub-processor-notice.md` | Anthropic as sub-processor — certifications and SCCs |
| `client-disclosure.md` | Suggested client-facing disclosure text |

## TODO (Legal Review)

- [ ] Legal review of DPIA template by qualified DPO
- [ ] Validate sub-processor notice against current Anthropic DPA
- [ ] Confirm client disclosure meets local regulatory requirements
- [ ] Review data retention periods against MSP's own retention policy
