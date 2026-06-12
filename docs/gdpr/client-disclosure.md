# Client Disclosure — AI-Powered Reporting

> **THIS IS NOT LEGAL ADVICE.** This is a suggested disclosure template. Have your legal counsel review and adapt it for your jurisdiction and client contracts. TODO markers indicate sections requiring customization.

## Suggested Disclosure Text

---

**AI-Assisted Reporting Disclosure**

As part of our managed services, we use AI-powered tools to generate analytical reports from your service desk data in Power BI.

**What this means:**
- Your service data (tickets, SLA metrics, resource allocation) is analyzed by an AI system (Anthropic Claude) to generate performance reports
- Before any data reaches the AI system, all identifying information (company names, contact names, email addresses) is automatically replaced with anonymous aliases
- The AI system never sees your real company name, employee names, or other personally identifiable information
- The anonymization mapping is stored only on our local systems and is never transmitted externally

**Data protection measures in place:**
- Multi-layer anonymization (deterministic aliasing + NLP-based PII detection)
- Data volume limits to prevent bulk extraction
- Encrypted storage of anonymization mappings
- Audit logging of all AI interactions
- Automatic cleanup of session data after TODO: [X] days

**Your rights:**
- You may request that we disable AI-powered reporting for your account at any time
- You may request details about how your data is processed under GDPR Articles 13-15
- Contact TODO: [your DPO/privacy contact] for data protection inquiries

---

TODO: Adapt this text for your specific client contracts and regulatory requirements.
