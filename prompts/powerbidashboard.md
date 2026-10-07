# Power BI Live Dashboard Generator

Build an interactive, cross-filtering HTML dashboard from Power BI data.

**Topic:** $ARGUMENTS

**If no topic is specified, ask the user what the dashboard should cover** (for example: SLA performance, revenue and billing, resource utilization, ticket volume).

---

## Data comes pre-anonymized

> Data comes pre-anonymized. The MCP server anonymizes every response before it reaches you:
> you will see aliases like `Client_A`, `Resource_1`, `Contact_3`, never real names. Do not
> add, remove, or second-guess anonymization, and do not invent placeholder names yourself.
> Build the output with the aliases exactly as returned. Real names are restored locally
> afterwards by the deanonymizer; the mapping never leaves the user's machine. When you filter
> a query to one entity, filter on its numeric id, not on an aliased name.

The company list in the dashboard (`DATA.dim.companies`) therefore holds aliases. That is expected.

---

## What this produces

One self-contained HTML file built on `templates/dashboard.html`:

- Filter bar: company and time range, cross-filtering every KPI, gauge, chart and the table client-side
- KPI cards (up to 2 rows of 4), gauge rings with targets, up to 4 Chart.js charts, a ranked company table
- Layout driven by a `DASH_CONFIG` JSON object
- Data in a star-schema `DATA` JSON object (dimensions + monthly facts)
- A DAX proof panel listing every query used, so `tools/verify_report.py` can re-run them

---

## CRITICAL OUTPUT RULES

1. **Copy the ENTIRE template.** All CSS, HTML and JavaScript from `templates/dashboard.html`. Replace only the three placeholders. Do not rewrite or "simplify" the template engine.
2. **Use REAL data** from DAX queries you actually ran. Never fabricate or round away rows. If a query returns 240 rows, `DATA.facts` has 240 entries.
3. **Never use `get_schema`.** It can return more than 10MB and crash the session.
4. **Every number traces to a query.** Each query you used goes in the DAX proof panel (Phase 6).

---

## Phase 1: Discover the data model

If you do not know the workspace and dataset yet:

```
list_workspaces()
list_datasets(workspace_id="<WORKSPACE_ID>")
```

If the user has set default IDs in `~/.powerbi-mcp/config.json` you can omit `workspace_id` / `dataset_id` below.

Run 2-4 searches based on the topic, then list measures:

```
search_schema(search_term="<keyword>")
list_measures()
```

Identify:

- The measures you will use
- The fact table and the date table (year and month columns)
- The company name column (the dashboard's filter dimension)

**Use the measure and table names you actually find. Never guess.**

---

## Phase 2: Design the dashboard

Plan before you query:

- **KPI cards** (4 per row, max 2 rows): row 1 high-level or financial, row 2 operational or quality
- **Gauges** (2-5): percentage or ratio metrics that have a target (SLA, utilization, CSAT)
- **Charts** (up to 4): main trend, volume comparison (created vs resolved), secondary trend, quality trend
- **Company table**: breakdown by company, 4-6 columns

Every metric must be computable from summed monthly facts (`sum`, `ratio`, `wavg`) or come from a single static query. Averages and percentages are never summed: pull the numerator and denominator as separate fields and use `ratio:` or `wavg:`.

Ready-made `DASH_CONFIG` examples live in `templates/configs/` (SLA, revenue, utilization, ticket volume, CSAT, patch compliance, endpoint health, project performance). Start from the closest one.

---

## Phase 3: Pull data via DAX

The dashboard filters client-side, so it needs **granular company x month** facts, not totals. Every metric that should respond to the filters has to be a column in query A. A metric that only exists as a single total (pipeline, backup rate) goes in query B and stays fixed when filters change. Limit history to the current and previous year.

### A. Company x month (main facts, required)

```
EVALUATE ADDCOLUMNS(
    FILTER(
        SUMMARIZE(<FactTable>, <CompanyTable>[<company_name>], <DateTable>[year], <DateTable>[month]),
        <DateTable>[year] >= YEAR(TODAY()) - 1
    ),
    "rev", [<Revenue measure>],
    "cost", [<Cost measure>],
    "hrs", [<Hours measure>]
)
ORDER BY <CompanyTable>[<company_name>], <DateTable>[year], <DateTable>[month]
```

### B. Static KPIs (not filterable)

```
EVALUATE ROW("pipeline_count", [<Pipeline count measure>], "pipeline_value", [<Pipeline value measure>])
```

Name each output column with the short field name you will use in `DATA` (`rev`, `cost`, `hrs`, `t_cr`, `t_res`, `fr_met`, ...). That keeps the mapping from query to dashboard obvious.

If a query result is very large, narrow it (fewer measures per query, or split by year) rather than truncating rows.

---

## Phase 4: Build DATA and DASH_CONFIG

### DATA (star schema)

```json
{
  "refreshed": "2026-01-31T08:00:00Z",
  "dim": {
    "companies": ["Client_A", "Client_B"]
  },
  "facts": [{"c": 0, "y": 2025, "m": 1, "rev": 12345, "hrs": 50}],
  "static_kpi": {"pipeline_count": 45}
}
```

- `c` is the integer index into `dim.companies`
- `y` and `m` are integers
- Include every row the DAX returned. Blank measure values become `0`
- Omit `static_kpi` when you have no static KPIs

### DASH_CONFIG

```json
{
  "title": "Dashboard Title",
  "subtitle": "What this dashboard shows",
  "sources": "Autotask PSA via Power BI",
  "filters": ["company", "time"],
  "kpi_rows": [[], []],
  "gauges": [],
  "charts": [],
  "table": {}
}
```

Use exactly `["company", "time"]`. The template can also draw resource and queue buttons, but its render loop only applies the company and time filters, so those buttons would do nothing.

### Metric syntax

| Syntax | Meaning |
|--------|---------|
| `sum:field` | Sum of the field across the filtered facts |
| `ratio:a:b` | sum(a) / sum(b) |
| `wavg:sum:count` | Weighted average: sum(sum) / sum(count) |
| `static:key` | Value from `DATA.static_kpi` |

### KPI card

```json
{"label": "Revenue", "color": "teal", "metric": "sum:rev", "format": "eur",
 "sub_metric": "ratio:profit:rev", "sub_format": "pct", "sub_prefix": "Margin "}
```

Use `"sub_text": "Target: 85%"` for a fixed subtitle instead of a sub-metric.

### Gauge

```json
{"label": "SLA Met", "metric": "ratio:fr_met:t_cr", "color": "#0f766e",
 "target": 0.85, "target_label": "Target: 85%", "max": 1}
```

### Chart

```json
{
  "title": "Revenue by Month", "badge": "Monthly", "full": false,
  "series": [
    {"label": "Revenue", "field": "rev", "color": "#0f766e", "type": "bar", "bg": "rgba(15,118,110,0.7)"},
    {"label": "CSAT", "compute": "ratio", "numerator": "csat_sum", "denominator": "csat_n",
     "color": "#2563eb", "type": "line", "tooltip_format": "rating"}
  ],
  "y_format": "eur"
}
```

### Company table

```json
{
  "title": "Top Companies by Revenue",
  "columns": [
    {"label": "#", "type": "rank"},
    {"label": "Company", "type": "name"},
    {"label": "Revenue", "field": "rev", "format": "eur"},
    {"label": "Rev/Hour", "type": "derived", "calc": "rev/hrs", "format": "eur"}
  ],
  "sort": "rev", "order": "desc", "limit": 15
}
```

**Colors:** `teal`, `blue`, `amber`, `green`, `red`, `purple`
**Formats:** `eur`, `pct`, `pct0`, `num`, `hrs`, `rating`

Every `field`, `numerator` and `denominator` you reference must exist in the facts. A typo renders as `--` or `0`.

---

## Phase 5: Generate the HTML

Take `templates/dashboard.html` from this repo and replace:

| Placeholder | Value |
|-------------|-------|
| `{{DASHBOARD_CONFIG}}` | Your `DASH_CONFIG` JSON |
| `{{DATA_JSON}}` | Your `DATA` JSON |
| `{{GENERATED_DATE}}` | Today's date |

If you can write files, save the result as `<slug>.html` (for example `sla-performance.html`) in the user's working directory. If you cannot write files (chat-only clients such as Copilot Studio), output the complete HTML in one code block so the user can save it.

---

## Phase 6: Append the DAX proof panel

After the final `</script>` of the template, append one panel that holds every query you ran, each with a `-- Result:` line for the headline figure it produced where one exists:

```html
<section data-screen-label="DAX queries" style="max-width:1280px;margin:0 auto 60px;padding:0 24px;font-family:'Open Sans',sans-serif;">
  <details class="dax-proof" style="border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;background:#f8fafc;">
    <summary style="cursor:pointer;font-weight:600;color:#0f766e;font-size:0.85rem;">DAX queries behind this dashboard</summary>
    <pre style="white-space:pre-wrap;font-family:'JetBrains Mono',monospace;font-size:0.72rem;line-height:1.6;background:#0f172a;color:#e2e8f0;padding:14px;border-radius:6px;margin-top:10px;">-- Company x month facts
EVALUATE ...

-- Static KPIs
-- Result: pipeline_count = 45
EVALUATE ROW(...)</pre>
  </details>
</section>
```

HTML-escape `<`, `>` and `&` inside the `<pre>`.

---

## Phase 7: Verify before you say it is done

1. **Placeholders gone:** the file contains no `{{`.
2. **JSON parses:** `DASH_CONFIG` and `DATA` are valid JSON (no trailing commas, no comments).
3. **Fields exist:** every field referenced in `DASH_CONFIG` appears in at least one fact row.
4. **Row counts match:** `DATA.facts` length equals the row count of query A.
5. **Numbers check out** (if the user can run Python locally):

   ```bash
   python3 tools/verify_report.py <slug>.html
   ```

Then tell the user:

- The file path (or that the HTML is in the code block above)
- Which measures and tables you used
- How to restore real names locally, either by running

  ```bash
  python -m server <slug>.html -o <slug>-real.html
  ```

  or by sharing only the anonymized version
- That the dashboard is a snapshot: re-run this prompt to refresh the numbers

---

## Reference: typical measures (Proxuma Power BI model)

Your model may differ. Always confirm with `search_schema` and `list_measures`.

- **Financial:** Revenue - Total, Cost - Total, Profit - total, Billable, Total (hours)
- **Tickets:** Tickets - Count - Created, Tickets - Count - Resolved, Tickets - Overdue, Open Tickets (Current)
- **SLA:** Tickets - First Response Met %, Tickets - Resolution Met %, Tickets - First Hour Fix %, Tickets - Same Day Resolution %
- **CSAT:** CSAT - Average Rating
- **Pipeline:** Pipeline - Count, Pipeline - Total Value, Pipeline - Weighted Value, Pipeline - Win Rate
- **Backup:** NAble - Backup Success Rate %, NAble - Total Active Devices, NAble - Total Protected Storage GB
- **Resources:** Resources - Active Count, Resources - Total Count, Resources - FTE Equivalent

Typical tables: `BI_Autotask_Time_Entries`, `BI_Autotask_Tickets`, `BI_Autotask_Companies`, `BI_Common_Dim_Date` (`year` and `month` are integers).

Percentage measures such as "First Response Met %" cannot be summed across months. For the dashboard, pull the underlying counts (met and total) and let `ratio:` compute the percentage.
