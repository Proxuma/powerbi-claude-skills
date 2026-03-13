# Power BI QBR Report Generator

Generate a Quarterly Business Review (QBR) report for a specific client using Power BI data.

**Customer:** $ARGUMENTS

**If no customer name is specified, ask the user which customer to generate the QBR for.**

## Purpose

This report is designed for MSP salespeople to bring to client meetings. It covers:
1. Value delivered (SLA performance, ticket resolution)
2. Upsell opportunities (expired warranties, inactive contracts)
3. Security gaps (aging devices, out-of-warranty assets)
4. Financial analysis (revenue, cost, margin, portfolio comparison)
5. Recommended actions for next quarter

---

## Step 0: Discover Workspace and Dataset

You need a workspace ID and dataset ID to run queries. **Do not hardcode these.**

1. Run `mcp__powerbi__list_workspaces()` to list available workspaces
2. If multiple workspaces exist, ask the user which one contains their PSA data
3. Run `mcp__powerbi__list_datasets(workspace_id="<WORKSPACE_ID>")` to list datasets
4. If multiple datasets exist, ask the user which one to use
5. Store the `dataset_id` for all subsequent queries

**CRITICAL: NEVER use `mcp__powerbi__get_schema`. It returns >10MB and will crash the session.**

Use `mcp__powerbi__search_schema` with specific terms and `mcp__powerbi__list_measures` to discover your data model.

---

## Step 1: Discover the Data Model

Every Power BI dataset is different. Before writing any DAX, you need to find the actual table and column names in this dataset.

Run these searches to map out the schema. Common PSA datasets (Autotask, ConnectWise, HaloPSA) use similar concepts but different naming.

```
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="company")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="ticket")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="configuration")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="contract")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="billing")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="resource")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="sla")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="warranty")
mcp__powerbi__search_schema(workspace_id="<WS>", dataset_id="<DS>", search_term="priority")
mcp__powerbi__list_measures(workspace_id="<WS>", dataset_id="<DS>")
```

### What You Are Looking For

Build a mental map of these concepts. The exact names will differ per dataset.

| Concept | Common Table Names | Common Column Names |
|---------|-------------------|---------------------|
| Companies | Companies, Accounts, Clients | company_id, company_name, account_name |
| Tickets | Tickets, ServiceTickets | ticket_id, ticket_type_name, status_name, priority_name, create_date, complete_datetime, category_name |
| SLA Metrics | (often measures, not columns) | first_response_met, resolution_met (frequently int 0/1) |
| Time Entries | TimeEntries, Time_Entries | hours_worked, hours_billed, resource_name |
| Config Items | ConfigurationItems, Assets, Devices | category_name, is_active, warranty_expiration_date |
| Contracts | Contracts | contract_name, contract_type, status, company_id |
| Billing | BillingItems, Invoices | total_amount, cost, posted_date |
| Resources | Resources, Technicians | resource_name, resource_id |

### DAX Gotchas

- **Integer boolean columns** (like `first_response_met`, `resolution_met`): These are often stored as int64. Filter them with `+ 0 = 1` instead of `= TRUE()`. Example: `'Tickets'[first_response_met] + 0 = 1`
- **Missing columns**: If `search_schema` does not return a column, it does not exist. Do not guess. Skip that section or find an alternative.
- **RELATED()**: Only works when a relationship exists between tables. If your filter is on a column in a different table, use CALCULATE with a filter instead.
- **TOPN()**: Always use TOPN for "top N" queries to limit result size.
- **Date filtering**: Use `DATE(YEAR(TODAY()), 1, 1)` for current year, or `TODAY() - 365` for trailing 12 months.

---

## Step 2: Find the Customer

Search for the customer by name. Adapt the table/column names based on what you found in Step 1.

```dax
EVALUATE
FILTER(
    'Companies',
    SEARCH("<CUSTOMER_NAME>", 'Companies'[company_name], 1, 0) > 0
)
```

If multiple results, ask the user which one. Store the `company_id` for all subsequent queries.

If no results, try partial matches or ask the user to verify the name.

---

## Step 3: Execute DAX Queries

Run these queries in 3 parallel batches. **Adapt all table names, column names, and measure names** to match what you discovered in Step 1. The queries below use example names from a typical Autotask PSA dataset.

### Batch 1: Core KPIs (run in parallel)

**Query 1A: Client Financial and SLA KPIs**
```dax
EVALUATE
ROW(
    "Revenue", CALCULATE([Revenue - Total], 'Companies'[company_id] = <ID>),
    "Cost", CALCULATE([Cost - Total], 'Companies'[company_id] = <ID>),
    "Profit", CALCULATE([Profit - total], 'Companies'[company_id] = <ID>),
    "Margin_Pct", CALCULATE([Profit - total - percentage], 'Companies'[company_id] = <ID>),
    "SLA_FR_Pct", CALCULATE([Tickets - First Response Met %], 'Companies'[company_id] = <ID>),
    "SLA_Res_Pct", CALCULATE([Tickets - Resolution Met %], 'Companies'[company_id] = <ID>),
    "Hours_Worked", CALCULATE([Company - Hours Worked], 'Companies'[company_id] = <ID>),
    "Hours_Billed", CALCULATE([Company - Hours Billed], 'Companies'[company_id] = <ID>),
    "Avg_Hrs_Per_Ticket", CALCULATE([Tickets - Avg Hours Per Ticket], 'Companies'[company_id] = <ID>)
)
```

**Query 1B: Ticket and CI Summary**
```dax
EVALUATE
ROW(
    "Total_Tickets", CALCULATE(COUNTROWS('Tickets'), 'Companies'[company_id] = <ID>),
    "Open_Tickets", CALCULATE(
        COUNTROWS(FILTER('Tickets', ISBLANK('Tickets'[complete_datetime]))),
        'Companies'[company_id] = <ID>
    ),
    "Total_CIs", CALCULATE(COUNTROWS('ConfigurationItems'), 'Companies'[company_id] = <ID>),
    "Active_CIs", CALCULATE(
        COUNTROWS(FILTER('ConfigurationItems', 'ConfigurationItems'[is_active] = TRUE())),
        'Companies'[company_id] = <ID>
    )
)
```

**Query 1C: Portfolio Benchmarks (all clients)**
```dax
EVALUATE
ROW(
    "Portfolio_Revenue", [Revenue - Total],
    "Portfolio_Margin", [Profit - total - percentage],
    "Portfolio_SLA_FR", [Tickets - First Response Met %],
    "Total_Companies", COUNTROWS(VALUES('Companies'[company_id])),
    "Total_Tickets", COUNTROWS('Tickets'),
    "Portfolio_Avg_Hrs", [Tickets - Avg Hours Per Ticket]
)
```

### Batch 2: Detailed Breakdowns (run in parallel)

**Query 2A: Ticket Types**
```dax
EVALUATE
ADDCOLUMNS(
    SUMMARIZE(
        FILTER('Tickets', RELATED('Companies'[company_id]) = <ID>),
        'Tickets'[ticket_type_name]
    ),
    "Count", CALCULATE(COUNTROWS('Tickets'), 'Companies'[company_id] = <ID>)
)
ORDER BY [Count] DESC
```

**Query 2B: Top 10 Ticket Categories**
```dax
EVALUATE
TOPN(10,
    ADDCOLUMNS(
        SUMMARIZE(
            FILTER('Tickets', RELATED('Companies'[company_id]) = <ID>),
            'Tickets'[ticket_category_name]
        ),
        "Count", CALCULATE(COUNTROWS('Tickets'), 'Companies'[company_id] = <ID>)
    ),
    [Count], DESC
)
ORDER BY [Count] DESC
```

**Query 2C: Top 10 Resources (will be anonymized)**
```dax
EVALUATE
TOPN(10,
    ADDCOLUMNS(
        SUMMARIZE(
            FILTER('TimeEntries', RELATED('Companies'[company_id]) = <ID>),
            'Resources'[resource_name]
        ),
        "Hours_Worked", CALCULATE([Company - Hours Worked], 'Companies'[company_id] = <ID>),
        "Hours_Billed", CALCULATE([Company - Hours Billed], 'Companies'[company_id] = <ID>)
    ),
    [Hours_Worked], DESC
)
ORDER BY [Hours_Worked] DESC
```

**Query 2D: CI Categories with Warranty Status**
```dax
EVALUATE
ADDCOLUMNS(
    SUMMARIZE(
        FILTER('ConfigurationItems',
            RELATED('Companies'[company_id]) = <ID>
            && 'ConfigurationItems'[is_active] = TRUE()),
        'ConfigurationItems'[configuration_item_category_name]
    ),
    "Count", CALCULATE(
        COUNTROWS('ConfigurationItems'),
        'Companies'[company_id] = <ID>,
        'ConfigurationItems'[is_active] = TRUE()
    ),
    "Expired_Warranty", CALCULATE(
        COUNTROWS(FILTER('ConfigurationItems',
            'ConfigurationItems'[warranty_expiration_date] < TODAY())),
        'Companies'[company_id] = <ID>,
        'ConfigurationItems'[is_active] = TRUE()
    )
)
ORDER BY [Count] DESC
```

### Batch 3: SLA and Contract Details (run in parallel)

**Query 3A: Priority Breakdown with SLA**
```dax
EVALUATE
ADDCOLUMNS(
    SUMMARIZE(
        FILTER('Tickets', RELATED('Companies'[company_id]) = <ID>),
        'Tickets'[priority_name]
    ),
    "Count", CALCULATE(COUNTROWS('Tickets'), 'Companies'[company_id] = <ID>),
    "FR_Met_Pct", CALCULATE([Tickets - First Response Met %], 'Companies'[company_id] = <ID>),
    "Res_Met_Pct", CALCULATE([Tickets - Resolution Met %], 'Companies'[company_id] = <ID>)
)
ORDER BY [Count] DESC
```

**Query 3B: Contract Summary**
```dax
EVALUATE
ADDCOLUMNS(
    SUMMARIZE(
        FILTER('Contracts', RELATED('Companies'[company_id]) = <ID>),
        'Contracts'[contract_name],
        'Contracts'[contract_type_name],
        'Contracts'[contract_status_name]
    ),
    "Revenue", CALCULATE([Revenue - Total], 'Companies'[company_id] = <ID>)
)
ORDER BY [Revenue] DESC
```

**Query 3C: Open Ticket Aging**
```dax
EVALUATE
ADDCOLUMNS(
    SUMMARIZE(
        FILTER('Tickets',
            RELATED('Companies'[company_id]) = <ID>
            && ISBLANK('Tickets'[complete_datetime])),
        'Tickets'[ticket_age_category]
    ),
    "Count", CALCULATE(
        COUNTROWS(FILTER('Tickets', ISBLANK('Tickets'[complete_datetime]))),
        'Companies'[company_id] = <ID>
    )
)
ORDER BY [Count] DESC
```

---

## Step 4: Generate the HTML Report

Generate a self-contained HTML file with all CSS inline. The report uses the `.prx-report` scoped CSS framework.

### Anonymization Rules

- **Resource names**: Replace all real names with "Resource A", "Resource B", "Resource C", etc.
- **Client name in the report title is fine** (the salesperson needs it), but do not expose other client names from portfolio data
- **No internal cost data should appear without the user's consent** (revenue and margin are OK for QBR context)

### Report Sections (in order)

The HTML report contains these sections, each numbered with its own collapsible DAX query:

**Header area:**
- Document header with report title, date, and metadata
- Demo data notice (yellow banner)
- Document title block: "Quarterly Business Review: [Company Name]"
- Subtitle: "Trailing 12-month analysis of service delivery, financial performance, and asset management"

**KPI row (4-column grid):**
- Revenue (with portfolio average comparison)
- Profit Margin % (green/red/amber note)
- SLA First Response % (green/red/amber note)
- Open Tickets (with total ticket count note)

**Section 1.0: Executive Financial Summary**
- Revenue, cost, profit, margin in a table
- Hours worked vs hours billed
- Comparison bar chart: client margin vs portfolio average margin

**Section 2.0: Service Delivery Overview**
- Ticket type distribution table (Service Request, Incident, Problem, Change, etc.)
- Donut chart showing the split

**Section 3.0: SLA Performance**
- Priority breakdown table: Priority | Count | First Response % | Resolution %
- Color-coded percentages (green >90%, amber 70-90%, red <70%)

**Section 4.0: Top Ticket Categories**
- Horizontal bar chart of top 10 categories
- Table with counts and percentages

**Section 5.0: Resolution Efficiency**
- Mini KPI cards: Avg hours/ticket, First hour fix rate (if available)
- Comparison to portfolio average

**Section 6.0: Resource Investment**
- Table of top 10 resources: Resource A, B, C... | Hours Worked | Hours Billed | Utilization %
- **All names anonymized**

**Section 7.0: Open Ticket Aging**
- Aging distribution: 0-7 days, 8-14 days, 15-30 days, 31-60 days, 60+ days
- Horizontal bar chart with color coding (green for fresh, red for aged)

**Section 8.0: Asset and Device Inventory**
- CI categories table: Category | Active Count | Expired Warranty Count
- Warranty risk percentage per category
- Flag categories where >30% have expired warranties

**Section 9.0: Contract Portfolio**
- All contracts table: Name | Type | Status
- Highlight inactive contracts as upsell opportunities

**Section 10.0: Portfolio Benchmark**
- Side-by-side comparison cards: Client vs Portfolio Average
- Metrics: Revenue, Margin, SLA FR%, Avg Hours/Ticket
- Arrow indicators (up/down) showing whether client is above or below average

**Section 11.0: Key Insights**
- 6 insight cards based on the data, each with a severity level:
  - `critical` (red): Urgent issues (e.g., SLA below 70%, many expired warranties)
  - `warning` (amber): Areas needing attention (e.g., aging tickets, low utilization)
  - `ok` (green): Positive findings (e.g., SLA above target, good margin)
- Each insight has a title and 2-3 sentence explanation

**Section 12.0: Recommended Actions for Next Quarter**
- 5-7 numbered, specific actions the salesperson can discuss with the client
- Each action references specific data from the report
- Examples: "Schedule hardware refresh for 12 devices with expired warranties in the Server category", "Review 3 inactive contracts for reactivation"

**Footer:**
- Report generation date
- "Generated via Power BI MCP" note

### Each Section Gets Its Own DAX Query

Every data section must have a collapsible DAX query at the bottom showing exactly what was queried. Use this HTML pattern:

```html
<div class="dax-toggle" onclick="this.classList.toggle('expanded')">
    <div class="dax-trigger">
        <svg class="dax-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 9l-7 7-7-7"/></svg>
        <span>View DAX Query: [Section Description]</span>
    </div>
    <div class="dax-content">
        <pre><code>EVALUATE ...</code></pre>
        <button class="dax-copy" onclick="event.stopPropagation();let c=this.closest('.dax-content').querySelector('code');navigator.clipboard.writeText(c.textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy Query',2000)">Copy Query</button>
    </div>
</div>
```

---

## Step 5: Insight and Action Generation

Based on the actual data returned, generate insights and actions. Be specific, reference real numbers.

**Insight generation rules:**
- Reference actual values from the data (e.g., "SLA First Response is at 82%, below the 90% target")
- Compare to portfolio averages where available
- Flag warranty expirations with specific counts
- Identify aging ticket clusters
- Note contract status issues

**Action generation rules:**
- Each action should be concrete and tied to data ("Review the 8 tickets open for 30+ days")
- Include the business case where possible ("Reactivating the Managed Backup contract could add ~$X/month")
- Order from highest impact to lowest
- Write for a salesperson who will read this aloud to a client

---

## Step 6: Assemble and Write the Full HTML

Below is the complete CSS framework and HTML skeleton. Fill in the data sections with actual query results.

### Complete CSS (inline in the HTML)

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QBR Report: [Company Name]</title>
<style>
/* === Reset & Base === */
.prx-report *,.prx-report *::before,.prx-report *::after{box-sizing:border-box;margin:0;padding:0;}
.prx-report{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;color:#333;line-height:1.7;max-width:1140px;margin:0 auto;padding:20px 24px;-webkit-font-smoothing:antialiased;}

/* === Teal Frame === */
.prx-report .report-frame-outer{background:linear-gradient(180deg,#0f766e 0%,#115e58 50%,#134e4a 100%);border-radius:12px;padding:50px;margin-bottom:40px;}
.prx-report .doc{background:white;border-radius:4px;box-shadow:0 2px 20px rgba(0,0,0,0.12),0 0 0 1px rgba(0,0,0,0.04);position:relative;}

/* === Document Header === */
.prx-report .doc-header{padding:36px 48px 28px;border-bottom:3px solid #1B365D;display:flex;justify-content:space-between;align-items:flex-start;}
.prx-report .doc-type{font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#94a3b8;}
.prx-report .doc-header-right{text-align:right;}
.prx-report .doc-header-right .doc-meta-row{font-size:0.74rem;color:#64748b;line-height:1.8;}
.prx-report .doc-header-right .doc-meta-row strong{color:#1B365D;font-weight:600;}

/* === Title Block === */
.prx-report .doc-title-block{padding:32px 48px 28px;border-bottom:1px solid #e2e8f0;}
.prx-report .doc-title{font-family:Georgia,'Times New Roman',serif;font-size:1.7rem;color:#1B365D;line-height:1.25;margin-bottom:8px;}
.prx-report .doc-subtitle{font-size:0.88rem;color:#64748b;line-height:1.6;}

/* === Demo Banner === */
.prx-report .doc-demo{margin:20px 48px 0;padding:12px 16px;background:#fefce8;border:1px solid #fde68a;border-radius:6px;font-size:0.8rem;color:#92400e;}
.prx-report .doc-demo strong{color:#78350f;}

/* === Document Body === */
.prx-report .doc-body{padding:0 48px;}

/* === Sections === */
.prx-report .doc-section{padding:28px 0;border-bottom:1px solid #f1f5f9;}
.prx-report .doc-section:last-child{border-bottom:none;}
.prx-report .doc-section-head{display:flex;align-items:baseline;gap:14px;margin-bottom:16px;}
.prx-report .doc-section-num{font-weight:800;font-size:0.82rem;color:#0f766e;flex-shrink:0;}
.prx-report .doc-section-title{font-weight:700;font-size:1rem;color:#1B365D;}
.prx-report .doc-section-sub{font-size:0.8rem;color:#64748b;margin-top:2px;}

/* === KPI Row === */
.prx-report .doc-kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;}
.prx-report .doc-kpi{padding:18px 20px;border-right:1px solid #e2e8f0;background:#fafbfc;}
.prx-report .doc-kpi:last-child{border-right:none;}
.prx-report .doc-kpi-label{font-size:0.66rem;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:#94a3b8;margin-bottom:4px;}
.prx-report .doc-kpi-value{font-size:1.6rem;font-weight:800;color:#1B365D;line-height:1.1;}
.prx-report .doc-kpi-note{font-size:0.72rem;margin-top:3px;}
.prx-report .doc-kpi-note.green{color:#10B981;}
.prx-report .doc-kpi-note.red{color:#ef4444;}
.prx-report .doc-kpi-note.amber{color:#f59e0b;}
.prx-report .doc-kpi-note.muted{color:#94a3b8;}

/* === Tables === */
.prx-report table{width:100%;border-collapse:collapse;font-size:0.85rem;}
.prx-report th{text-align:left;padding:10px 12px;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.4px;color:#64748b;background:#f8fafc;border-bottom:2px solid #e2e8f0;font-weight:600;}
.prx-report td{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle;}
.prx-report tbody tr:hover td{background:#f8fafc;}
.prx-report .num{font-weight:700;font-size:0.9rem;text-align:right;}
.prx-report .num-danger{color:#dc2626;}
.prx-report .num-warn{color:#d97706;}
.prx-report .num-ok{color:#16a34a;}

/* === Badges === */
.prx-report .pill{display:inline-block;padding:3px 10px;border-radius:10px;font-size:0.72rem;font-weight:600;white-space:nowrap;}
.prx-report .pill-blue{background:#dbeafe;color:#1e40af;}
.prx-report .pill-green{background:#d1fae5;color:#065f46;}
.prx-report .pill-amber{background:#fef3c7;color:#92400e;}
.prx-report .pill-red{background:#fee2e2;color:#991b1b;}
.prx-report .pill-gray{background:#f1f5f9;color:#475569;}
.prx-report .pct-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600;}
.prx-report .pct-ok{background:#d1fae5;color:#065f46;}
.prx-report .pct-mid{background:#fef3c7;color:#92400e;}
.prx-report .pct-bad{background:#fee2e2;color:#991b1b;}

/* === Horizontal Bar Chart === */
.prx-report .hbar-chart{margin:12px 0;}
.prx-report .hbar-row{display:flex;align-items:center;gap:10px;margin-bottom:6px;}
.prx-report .hbar-label{width:160px;font-size:0.78rem;color:#334155;text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.prx-report .hbar-track{flex:1;height:22px;background:#f1f5f9;border-radius:4px;overflow:hidden;}
.prx-report .hbar-fill{height:100%;border-radius:4px;min-width:2px;transition:width 0.3s ease;}
.prx-report .hbar-fill.teal{background:#0f766e;}
.prx-report .hbar-fill.blue{background:#3b82f6;}
.prx-report .hbar-fill.amber{background:#f59e0b;}
.prx-report .hbar-fill.red{background:#ef4444;}
.prx-report .hbar-fill.green{background:#10B981;}
.prx-report .hbar-val{width:50px;font-size:0.78rem;font-weight:700;color:#1B365D;}

/* === Donut Chart (SVG) === */
.prx-report .donut-wrap{display:flex;align-items:center;gap:24px;margin:16px 0;}
.prx-report .donut-legend{display:flex;flex-direction:column;gap:6px;}
.prx-report .donut-legend-item{display:flex;align-items:center;gap:8px;font-size:0.8rem;color:#334155;}
.prx-report .donut-legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}

/* === Comparison Cards === */
.prx-report .compare-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:12px 0;}
.prx-report .compare-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;text-align:center;}
.prx-report .compare-card-label{font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:6px;}
.prx-report .compare-card-value{font-size:1.4rem;font-weight:800;color:#1B365D;line-height:1.2;}
.prx-report .compare-card-sub{font-size:0.72rem;margin-top:4px;}
.prx-report .compare-card.highlight{border-color:#0f766e;border-width:2px;}

/* === Findings / Insights === */
.prx-report .doc-finding{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #f1f5f9;}
.prx-report .doc-finding:last-child{border-bottom:none;}
.prx-report .doc-finding-icon{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:0.72rem;font-weight:800;color:white;margin-top:2px;}
.prx-report .doc-finding-icon.critical{background:#ef4444;}
.prx-report .doc-finding-icon.warning{background:#f59e0b;}
.prx-report .doc-finding-icon.ok{background:#10B981;}
.prx-report .doc-finding-body h4{font-size:1rem;font-weight:700;margin:0 0 4px 0;line-height:1.3;color:#0f172a;}
.prx-report .doc-finding-body p{font-size:0.85rem;color:#475569;line-height:1.7;margin:0;}

/* === Narrative === */
.prx-report .narrative{margin:8px 0;}
.prx-report .narrative p{font-size:0.9rem;line-height:1.8;color:#334155;margin-bottom:14px;}
.prx-report .narrative p:last-child{margin-bottom:0;}
.prx-report .narrative strong{color:#1B365D;}

/* === DAX Toggle === */
.prx-report .dax-toggle{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;margin-top:16px;}
.prx-report .dax-toggle .dax-trigger{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;font-size:0.78rem;font-weight:600;color:#0f766e;background:#f1f5f9;user-select:none;}
.prx-report .dax-chevron{width:16px;height:16px;flex-shrink:0;transition:transform 0.25s ease;}
.prx-report .dax-toggle.expanded .dax-chevron{transform:rotate(180deg);}
.prx-report .dax-content{max-height:0;overflow:hidden;transition:max-height 0.3s ease;}
.prx-report .dax-toggle.expanded .dax-content{max-height:600px;}
.prx-report .dax-content pre{padding:14px 16px;background:#0f172a;border-radius:0;}
.prx-report .dax-content code{font-family:'Courier New',Courier,monospace;font-size:0.72rem;line-height:1.65;color:#e2e8f0;background:transparent;}
.prx-report .dax-copy{display:block;margin:8px 16px 12px auto;border:none;border-radius:4px;padding:5px 14px;font-size:0.72rem;font-weight:600;cursor:pointer;font-family:inherit;background:#14b8a6;color:white;}
.prx-report .dax-copy:hover{background:#0d9488;}

/* === Actions List === */
.prx-report .action-list{counter-reset:action;}
.prx-report .action-item{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #f1f5f9;counter-increment:action;}
.prx-report .action-item:last-child{border-bottom:none;}
.prx-report .action-num{width:28px;height:28px;border-radius:50%;background:#0f766e;color:white;display:flex;align-items:center;justify-content:center;font-size:0.72rem;font-weight:800;flex-shrink:0;margin-top:2px;}
.prx-report .action-body h4{font-size:0.92rem;font-weight:700;color:#0f172a;margin:0 0 4px 0;}
.prx-report .action-body p{font-size:0.84rem;color:#475569;line-height:1.6;margin:0;}

/* === Footer === */
.prx-report .doc-footer{margin-top:16px;padding:16px 48px;border-top:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;}
.prx-report .doc-footer span{font-size:0.68rem;color:#94a3b8;}

/* === Responsive === */
@media(max-width:900px){
    .prx-report .report-frame-outer{padding:28px;}
    .prx-report .doc-kpi-row{grid-template-columns:repeat(2,1fr);}
    .prx-report .compare-grid{grid-template-columns:1fr;}
    .prx-report .doc-header{flex-direction:column;gap:12px;}
    .prx-report .doc-header-right{text-align:left;}
}
@media(max-width:600px){
    .prx-report .report-frame-outer{padding:16px;}
    .prx-report .doc-kpi-row{grid-template-columns:1fr;}
    .prx-report .doc-body{padding:0 20px;}
    .prx-report .doc-header,.prx-report .doc-title-block{padding-left:20px;padding-right:20px;}
    .prx-report .doc-demo{margin-left:20px;margin-right:20px;}
    .prx-report .doc-footer{padding-left:20px;padding-right:20px;}
    .prx-report .hbar-label{width:100px;}
}

/* === Print === */
@media print{
    .prx-report .dax-toggle{display:none;}
    .prx-report .dax-copy{display:none;}
    .prx-report .doc-section{break-inside:avoid;}
}
</style>
</head>
<body>
<div class="prx-report">
<!-- Report content here -->
</div>
</body>
</html>
```

### HTML Structure Skeleton

Use this structure. Fill in each section with the actual data from the DAX queries.

```html
<div class="prx-report">
<div class="report-frame-outer">
<div class="doc">

    <!-- Header -->
    <div class="doc-header">
        <div>
            <div class="doc-type">Quarterly Business Review</div>
        </div>
        <div class="doc-header-right">
            <div class="doc-meta-row"><strong>Date:</strong> [TODAY]</div>
            <div class="doc-meta-row"><strong>Period:</strong> Trailing 12 months</div>
            <div class="doc-meta-row"><strong>Source:</strong> Power BI via MCP</div>
        </div>
    </div>

    <!-- Title -->
    <div class="doc-title-block">
        <h1 class="doc-title">Quarterly Business Review: [Company Name]</h1>
        <p class="doc-subtitle">Service delivery, financial performance, and asset management analysis for the trailing 12-month period.</p>
    </div>

    <!-- Demo banner (optional, remove if using real data) -->
    <div class="doc-demo">
        <strong>Note:</strong> This report was generated from your Power BI dataset. All resource names have been anonymized.
    </div>

    <div class="doc-body">

        <!-- KPI Row -->
        <div class="doc-section">
            <div class="doc-kpi-row">
                <div class="doc-kpi">
                    <div class="doc-kpi-label">Revenue</div>
                    <div class="doc-kpi-value">[VALUE]</div>
                    <div class="doc-kpi-note muted">Portfolio avg: [VALUE]</div>
                </div>
                <div class="doc-kpi">
                    <div class="doc-kpi-label">Profit Margin</div>
                    <div class="doc-kpi-value">[VALUE]%</div>
                    <div class="doc-kpi-note [green/red/amber]">[Above/Below] portfolio avg</div>
                </div>
                <div class="doc-kpi">
                    <div class="doc-kpi-label">SLA First Response</div>
                    <div class="doc-kpi-value">[VALUE]%</div>
                    <div class="doc-kpi-note [green/red/amber]">[Status text]</div>
                </div>
                <div class="doc-kpi">
                    <div class="doc-kpi-label">Open Tickets</div>
                    <div class="doc-kpi-value">[VALUE]</div>
                    <div class="doc-kpi-note muted">of [TOTAL] total</div>
                </div>
            </div>
        </div>

        <!-- Section 1.0: Executive Financial Summary -->
        <div class="doc-section">
            <div class="doc-section-head">
                <span class="doc-section-num">1.0</span>
                <span class="doc-section-title">Executive Financial Summary</span>
            </div>
            <p class="doc-section-sub">Revenue, cost, profit, and margin for the trailing 12-month period.</p>
            <!-- Table and chart here -->
            <!-- DAX toggle here -->
        </div>

        <!-- Section 2.0 through 12.0 follow the same pattern -->
        <!-- ... -->

    </div>

    <!-- Footer -->
    <div class="doc-footer">
        <span>Generated [DATE] via Power BI MCP</span>
        <span>Quarterly Business Review</span>
    </div>

</div>
</div>
</div>
```

### Chart Patterns

**Horizontal bar chart:**
```html
<div class="hbar-chart">
    <div class="hbar-row">
        <span class="hbar-label">[Category Name]</span>
        <div class="hbar-track">
            <div class="hbar-fill teal" style="width:[PERCENT]%"></div>
        </div>
        <span class="hbar-val">[COUNT]</span>
    </div>
    <!-- Repeat for each row -->
</div>
```

**Donut chart (inline SVG):**
```html
<div class="donut-wrap">
    <svg width="120" height="120" viewBox="0 0 120 120">
        <!-- Each segment is a circle with stroke-dasharray and stroke-dashoffset -->
        <circle cx="60" cy="60" r="45" fill="none" stroke="#0f766e" stroke-width="20"
            stroke-dasharray="[SEGMENT_LENGTH] [REMAINDER]"
            stroke-dashoffset="[OFFSET]"
            transform="rotate(-90 60 60)"/>
        <!-- Additional segments with different colors -->
    </svg>
    <div class="donut-legend">
        <div class="donut-legend-item">
            <span class="donut-legend-dot" style="background:#0f766e"></span>
            [Label] ([PERCENT]%)
        </div>
        <!-- Repeat -->
    </div>
</div>
```

The circumference of the donut is `2 * PI * 45 = 282.74`. Each segment's `stroke-dasharray` first value is `282.74 * percent / 100`. The `stroke-dashoffset` for each subsequent segment is the negative sum of previous segments' lengths.

**Comparison bar (client vs portfolio):**
```html
<div class="compare-grid">
    <div class="compare-card highlight">
        <div class="compare-card-label">[Company Name]</div>
        <div class="compare-card-value">[VALUE]</div>
        <div class="compare-card-sub green">Above average</div>
    </div>
    <div class="compare-card">
        <div class="compare-card-label">Portfolio Average</div>
        <div class="compare-card-value">[VALUE]</div>
        <div class="compare-card-sub muted">[N] companies</div>
    </div>
</div>
```

**Finding/insight card:**
```html
<div class="doc-finding">
    <div class="doc-finding-icon critical">!</div>
    <div class="doc-finding-body">
        <h4>[Insight Title]</h4>
        <p>[2-3 sentence explanation with specific numbers from the data]</p>
    </div>
</div>
```

**Action item:**
```html
<div class="action-item">
    <div class="action-num">[N]</div>
    <div class="action-body">
        <h4>[Action Title]</h4>
        <p>[Specific action with data reference and business case]</p>
    </div>
</div>
```

---

## Step 7: Save and Open

1. Determine the output filename: `qbr-[company-name-lowercase]-[YYYY-MM-DD].html`
2. Save the file to the current working directory
3. Open in browser:
   ```bash
   open ./qbr-[company-name].html
   ```
4. Tell the user: "QBR report saved and opened in your browser."

---

## Error Handling

- If a DAX query fails, check column names against what `search_schema` returned. Try alternative column names.
- If a measure does not exist, use `search_schema` to find the correct name. If no matching measure exists, compute it manually (e.g., `DIVIDE(SUM(...), COUNT(...))`) or skip that section.
- If a company has no data for a section (no CIs, no contracts), show "No data available for this section" instead of leaving it empty.
- If the report HTML is too large for a single write call, split the write into two parts (CSS + first half, then second half appended).
- If `RELATED()` fails, the tables may not have a relationship. Use `CALCULATE` with explicit filters instead.

---

## Writing Style for Narrative Sections

Write report text like a person who looked at the data and is summarizing it for a colleague. Specifically:

- Use concrete numbers ("12 tickets open for 30+ days") over vague statements ("several aging tickets")
- Avoid inflated language: no "crucial", "vital", "key", "significant", "notable"
- Avoid AI vocabulary: no "delve", "landscape", "foster", "leverage", "holistic", "robust"
- No promotional tone: no "game-changing", "powerful", "cutting-edge"
- No "It's not just X; it's Y" patterns
- No "Moreover", "Furthermore", "It's worth noting that"
- Keep sentences varied in length. Mix short and medium.
- Write directly: "Margin is 34%, 6 points above the portfolio average" instead of "The margin of 34% serves as a testament to the strong financial performance"
