# Data Protection Impact Assessment (DPIA) — Power BI AI Reporting

> **THIS IS NOT LEGAL ADVICE.** This template must be reviewed and completed by your Data Protection Officer (DPO) or legal counsel. TODO markers indicate sections requiring your organization's specific input.

## 1. Description of Processing

| Field | Value |
|-------|-------|
| **Processing activity** | AI-powered analysis and reporting of Power BI service desk data |
| **Controller** | TODO: [Your MSP name and registration details] |
| **Processor** | Proxuma (anonymization layer provider) |
| **Sub-processor** | Anthropic (Claude LLM inference) |
| **Data subjects** | MSP clients, their employees, IT contacts |
| **Categories of data** | Service desk tickets, SLA metrics, resource names, client names, contact information |
| **Purpose** | Generate analytical reports from Power BI data using LLM capabilities |
| **Legal basis** | TODO: [Art. 6(1)(f) legitimate interest / Art. 6(1)(b) contract performance / other] |

## 2. Necessity and Proportionality

| Question | Assessment |
|----------|-----------|
| Is the processing necessary for the stated purpose? | Yes. LLM analysis requires data input. Anonymization minimizes data exposure. |
| Could the purpose be achieved with less data? | Partially. DAX row limits (default 5,000) and free-text column redaction reduce scope. TODO: Configure `free_text_columns` for your dataset. |
| Is the data minimized? | Yes. Entity Registry + Presidio NLP anonymize PII before it reaches the LLM. |
| How long is data retained? | Mapping files: configurable (default 90 days, auto-cleanup). Anthropic: per their DPA (TODO: verify current terms). |

## 3. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PII leaks through anonymization gaps | Low | High | Four-layer anonymization (registry, Presidio, Dutch names, financial noise) |
| Mapping file theft (laptop loss) | Medium | High | Optional Fernet encryption with OS keychain storage |
| Prompt injection via data content | Low | Medium | Data boundary markers on all API responses |
| Bulk data extraction by LLM | Low | Medium | DAX row limit (5,000), schema size limit (500KB) |
| Re-identification from financial patterns | Low | Medium | Optional financial anonymization with deterministic noise |
| Audit trail gaps | Low | Low | Audit logging with daily rotation, 90-day retention |

## 4. Measures to Address Risks

TODO: Review each measure and confirm it meets your organization's requirements.

- [ ] Presidio with `en_core_web_lg` model enabled
- [ ] Dutch name detection enabled (if processing Dutch data)
- [ ] Mapping encryption enabled (`encrypt_mappings: true`)
- [ ] Free-text columns configured for your dataset
- [ ] Financial anonymization enabled (if processing financial data)
- [ ] Audit logging active
- [ ] Rate limiting configured
- [ ] Client disclosure provided
- [ ] Staff trained on deanonymization procedures
- [ ] Incident response procedure documented

## 5. Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Data Protection Officer | TODO | TODO | |
| IT Manager | TODO | TODO | |
| Project Owner | TODO | TODO | |
