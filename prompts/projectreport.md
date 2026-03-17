# Project Report Generator

Generate TWO professional HTML project reports with PDF export from Power BI / Autotask PSA data:
1. **External Report** - Customer-facing (customer branding, no financial data, resource names anonymized)
2. **Internal Report** - MSP internal use (MSP branding, full financial data, real names, profitability analysis)

## Usage
The user will specify which customer/project to generate a report for: $ARGUMENTS

**If no project is specified, ask the user which project they want a report for.**

---

## Setup: Customer & MSP Branding

When invoked, collect this information before generating reports:

### Required inputs
1. **Customer website URL** — used to extract branding for the External report
2. **MSP website URL** — used to extract branding for the Internal report

If the user provides these as arguments (e.g., `#projectreport Acme Corp https://acme.com https://yourmsp.com`), skip the questions.

If not provided, ask:
- "What is your customer's website URL? (for branding the external report)"
- "What is your company's website URL? (for branding the internal report)"

### Optional inputs
- **Language:** By default, detect language from each website. The user can override:
  - "Both in English" / "Both in Dutch" / "External in German, internal in English"
  - If not specified: External report uses customer's website language, Internal uses MSP's website language
- **Branding overrides:** The user can provide specific colors, logo URLs, or company names instead of auto-detection

### Auto-extraction workflow
For each website URL:
1. Fetch the homepage
2. Extract: company name (from `<title>` or logo alt text), logo URL (from header `<img>` or favicon), primary color (from CSS/meta theme-color), secondary color, language (from `<html lang="...">` or content analysis)
3. Map extracted colors to the CSS variable system (see Branding section below)

If extraction fails for any element, fall back to the default palette and ask the user to provide the missing info.

---

## BRANDING

### External Report
Uses the **customer's** branding (extracted from their website URL):
- `--navy-primary`: Customer's primary color → headers, title backgrounds
- `--brand-blue`: Customer's secondary color → borders, accents
- `--navy-dark`: Darker variant of customer's primary → deep backgrounds
- `--blue-bright`: Customer's accent color → links, highlights
- `--green-cta`: Customer's CTA color → buttons, export bar
- Logo: Customer's logo in header
- Company name: Customer's name in footer, copyright

### Internal Report
Uses the **MSP's** branding (extracted from their website URL):
- Same CSS variable mapping but with MSP's colors
- Logo: MSP's logo
- Company name: MSP name in footer
- Adds "INTERNAL USE ONLY" banner in red

### Fallback
If no website URLs are provided or extraction fails, use the default palette:
```css
:root {
    --navy-primary: #1B365D;
    --brand-blue: #164487;
    --navy-dark: #0f2240;
    --blue-bright: #60a5fa;
    --green-cta: #00D9A5;
    /* Functional colors (always unchanged): */
    --green-success: #10B981;
    --amber-warning: #F59E0B;
    --red-danger: #EF4444;
}
```

For Gantt bar colors, budget bar gradients, and pill badges: use `linear-gradient(135deg, primary, secondary)` with the extracted palette. Semantic colors (green for success, amber for warning, red for danger) stay unchanged.

**What stays the same regardless of branding:**
- Overall layout structure (export bar, header, content sections, footer)
- Typography system (Montserrat headings, Inter body, from Google Fonts)
- 8px spacing system
- Report sections and data presentation
- Internal/External report differentiation logic
- Gantt chart implementation
- DAX verification section (internal only)

## LANGUAGE

Reports can be generated in any language. The default behavior:

| Report | Language source | Example |
|--------|---------------|---------|
| External | Customer website `<html lang>` | `lang="de"` → German report |
| Internal | MSP website `<html lang>` | `lang="nl"` → Dutch report |

### What gets translated
- All headings and labels (e.g., "Executive Summary" → "Samenvatting")
- Status pills (e.g., "On Track" → "Op Schema")
- Section descriptions and narrative text
- Date formats (e.g., "March 17, 2026" → "17 maart 2026")
- Currency formatting (if applicable)

### What stays in English
- DAX query code blocks
- Technical field names in the DAX verification section (internal only)
- CSS class names and HTML structure

---

## Instructions

### 1. Discover Workspace and Dataset

**CRITICAL: NEVER use `mcp__powerbi__get_schema` - it returns >10MB and crashes the system!**

**Step 1: Find the workspace**
```
mcp__powerbi__list_workspaces()
```
Pick the workspace containing Autotask PSA data. If multiple workspaces exist, ask the user which one to use.

**Step 2: Find the dataset**
```
mcp__powerbi__list_datasets(workspace_id="<WORKSPACE_ID>")
```
Pick the dataset that contains project/task/time entry data.

**Step 3: Explore the schema (lightweight)**

| Need | Tool | Example |
|------|------|---------|
| Find specific measures/columns | `search_schema` | `search_schema(workspace_id="...", dataset_id="...", search_term="project")` |
| List all measure names | `list_measures` | `list_measures(workspace_id="...", dataset_id="...")` |
| Query actual data | `execute_dax` | `execute_dax(dataset_id="...", dax_query="EVALUATE ...")` |

### 2. Query Project Data

**Key Tables (typical Autotask PSA data model):**
- Projects table (e.g., `BI_Autotask_Projects`) - Project details
- Tasks table (e.g., `BI_Autotask_Tasks`) - Task breakdown by phase
- Time Entries table (e.g., `BI_Autotask_Time_Entries`) - Time entries by resource

Use `search_schema` with terms like "project", "task", "time", "phase", "resource" to find the actual table and column names in the user's data model.

**DAX Query Tips (Keep Results Small):**
- Always use `TOPN()` or `FILTER()` to limit results
- Select only needed columns, not entire tables
- Filter by project name early in the query
- Example:
```dax
EVALUATE
FILTER(
    SELECTCOLUMNS(
        'BI_Autotask_Projects',
        "Name", [ProjectName],
        "Client", [CompanyName],
        "Status", [Status]
    ),
    [Name] = "Project Name Here"
)
```

### 3. Generate BOTH Reports

You MUST generate two separate HTML files for every project.

---

## NAME HANDLING

### External Report (customer-facing)
- **Customer/company name:** Use REAL name (this report is for them)
- **Project name:** Use REAL name
- **MSP resource names:** Anonymize with common American names (the customer doesn't need to know individual tech names)
- **MSP company name:** Use REAL name (your logo is on it)

### Internal Report (MSP team)
- **All names:** Use REAL names — no anonymization (this report is for internal use only)
- **Customer name, project name, resource names:** All real

### When anonymization IS appropriate
If the user explicitly asks for demo/sample reports, or if they're generating reports for a portfolio/showcase, apply full anonymization:

**Person Names (for demo mode):**
Replace with common American first + last name combinations:
- Michael Johnson, Sarah Williams, David Anderson, Jennifer Miller
- Christopher Davis, Emily Wilson, Matthew Brown, Amanda Taylor
- James Peterson, Robert Collins, William Stevens, Thomas Mitchell

**Customer/Company Names (for demo mode):**

| Industry | Pattern Examples |
|----------|------------------|
| **Banks** | Riverside Bank, Summit State Bank, First Heritage Bank |
| **Credit Unions** | Lakeside Credit Union, Heritage Federal Credit Union |
| **Companies** | Precision Industries Inc., Northland Services LLC |
| **Construction** | Eastbrook Construction, Ridgeline Builders |
| **Cities** | City of Westfield, City of Lakewood, City of Fairmont |
| **Healthcare** | Northside Medical Clinic, Family Health Associates |
| **Non-Profits** | Heritage Community Foundation, Discovery Science Museum |

### Anonymization Rules (when applicable)
1. Create a consistent mapping: same original name = same replacement throughout BOTH reports
2. Keep project TYPE/STRUCTURE intact, only replace identifiable names
3. BOTH reports use the EXACT SAME anonymized names
4. NEVER show original names in console output or your response messages

---

## REPORT 1: External (Customer-Facing)

**Filename:** `Project_[ProjectName]_Report.html`

**Key Rules:**
- DO NOT include any financial data: no profit, costs, revenue, margins
- DO NOT include resource utilization cost details
- Focus on deliverables, timeline, and achievements

**Sections (top to bottom):**

1. **Export Bar** - Fixed at top, navy background, green CTA "Export as PDF" button (`onclick="window.print()"`)
2. **Header** - Logo area + meta (date, document number, period) separated by blue border
3. **Title Section** - Gradient background, project name, client name, status badge, details grid (project number, PM, contact, go-live date)
4. **Metric Cards** - 4-column grid: Progress (%), Budget used (no dollar amounts, just % or hours), Duration (days), Open risks. With progress bars where applicable. First card uses `.highlight` style (gradient bg)
5. **Key Deliverables** - 2x2 grid with icon cards showing completed/in-progress deliverables
6. **Project Timeline (Gantt chart)** - MANDATORY. Pure CSS table-based Gantt with phase bars, today marker
7. **Phase Summary Table** - Hours per phase with status pills, budget/spent/remaining columns, footer totals
8. **Budget Bar Chart** - Visual bar chart showing spent vs. budget per phase with colored bars (ok/warn/over)
9. **Management Summary** - Narrative summary of project status, 2-3 paragraphs
10. **Resource Overview** - Table with anonymized resource names, role, hours this period, total spent, budget, available
11. **Completed Work** - Checklist with green checkmarks
12. **Planned Work** - Checklist with circle icons
13. **Risks & Issues** - Table with #, risk, impact, likelihood, status pills, mitigation
14. **Decision Points** - Numbered decision list with deadlines (decision-date badges)
15. **Findings** - 2x2 grid with colored summary cards (.success, .warning, .info)
16. **Footer** - Logo area left, generated-by + website + copyright right

---

## REPORT 2: Internal (MSP Use)

**Filename:** `INTERNAL_Project_[ProjectName]_Report.html`

**Name handling:** Use REAL names throughout (see NAME HANDLING section). Customer name, project name, resource names — all real. This is an internal document.
- The only differences from external: Internal includes financial data, DAX queries, real resource names, and confidential banner
- If generating in demo mode, use the same anonymized names as the External report

**Additional Sections (beyond everything in the external report):**

- **Red "INTERNAL USE ONLY" banner** at top (fixed, above export bar)
- **"CONFIDENTIAL - INTERNAL" label** in export bar and header
- **Financial Overview** (4 cards): Revenue, Cost, Profit, Margin %
  - Color code margin: Green >40%, Yellow 25-40%, Red <25%
- **Budget Analysis** (4 cards): Budgeted Hours, Actual Hours, Variance, Efficiency %
- **Performance Indicators** (traffic lights): Schedule, Budget, Margin
- **Project Timeline (Gantt chart)** - MANDATORY (same as external)
- **Resource Utilization Table**: Team Member, Role, Hours, Est. Cost, % of Total
- **Lessons Learned Section**:
  - "What Went Well" (green checkmarks)
  - "Areas for Improvement" (orange warnings)
  - "Recommendations for Similar Projects" (blue arrows)
- **DAX Verification Section** - MANDATORY (see below)
- **Footer with "CONFIDENTIAL - INTERNAL USE ONLY"**

**Internal Report Styling:**
```css
--internal-red: #DC2626;
--internal-red-light: #FEE2E2;
--warning-yellow: #F59E0B;
```

### Quick Reference: External vs Internal Differences

| Element | External Report | Internal Report |
|---------|-----------------|-----------------|
| Top banner | None | Red "INTERNAL USE ONLY - CONFIDENTIAL" |
| Export bar title | "Project Status Report Preview" | "Internal Project Report" + confidential label |
| Header border | 3px solid `--brand-blue` | 3px solid `--internal-red` |
| Document prefix | `RPT-` | `INT-` |
| Footer border | 2px solid `--brand-blue` | 2px solid `--internal-red` |
| Footer tagline | Your company tagline | "CONFIDENTIAL - INTERNAL USE ONLY" |
| Page wrapper padding-top | 80px | 112px (accounts for banner) |

---

## DAX VERIFICATION SECTION - MANDATORY (Internal Report Only)

The internal report MUST include a collapsible section at the end showing ALL DAX queries used to generate the report data. This allows verification in Power BI Desktop.

### DAX Section HTML Structure
```html
<div class="section-label"><span>DAX Queries - Data Verification</span></div>
<div class="dax-section">
    <p class="dax-intro">Copy these queries to Power BI Desktop (View > Performance Analyzer) to verify the data in this report.</p>

    <div class="dax-query">
        <div class="dax-header" onclick="this.parentElement.classList.toggle('expanded')">
            <span class="dax-title">1. Project Details</span>
            <span class="dax-toggle-icon">&#9660;</span>
        </div>
        <div class="dax-content">
            <pre><code>EVALUATE
TOPN(5, FILTER(
    SELECTCOLUMNS('BI_Autotask_Projects', ...),
    [StartDate] = ...
), [ActualHours], DESC)</code></pre>
            <button class="copy-btn" onclick="copyDAX(this)">Copy Query</button>
        </div>
    </div>

    <!-- Repeat for each query used -->
</div>
```

### DAX Section CSS
```css
.dax-section {
    background: #f8fafc;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: var(--space-lg);
    margin-bottom: var(--space-2xl);
}

.dax-intro {
    font-size: 13px;
    color: var(--gray-600);
    margin-bottom: var(--space-lg);
}

.dax-query {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-bottom: 12px;
    overflow: hidden;
}

.dax-header {
    padding: 12px 16px;
    background: var(--navy-primary);
    color: white;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: 'Montserrat', sans-serif;
    font-size: 13px;
    font-weight: 600;
}

.dax-header:hover { background: #234B7A; }

.dax-toggle-icon { transition: transform 0.2s; }
.dax-query.expanded .dax-toggle-icon { transform: rotate(180deg); }

.dax-content {
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease;
}

.dax-query.expanded .dax-content { max-height: 500px; }

.dax-content pre {
    background: #1e293b;
    color: #e2e8f0;
    padding: 16px;
    margin: 0;
    overflow-x: auto;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 12px;
    line-height: 1.5;
}

.copy-btn {
    margin: 12px;
    padding: 8px 16px;
    background: var(--green-cta);
    color: var(--navy-primary);
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 600;
    font-size: 12px;
}

.copy-btn:hover { background: #00c49a; }
```

### DAX Section JavaScript
```javascript
function copyDAX(btn) {
    const code = btn.parentElement.querySelector('code').textContent;
    navigator.clipboard.writeText(code).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy Query'; }, 2000);
    });
}
```

### Required DAX Queries to Include
Include ALL queries actually used to generate the report:
1. **Project Details** - Main project info (name, client, lead, dates, financials)
2. **Task Breakdown** - Tasks by phase with hours
3. **Phase Summary** - Aggregated phase data
4. **Resource Utilization** - Time entries by resource
5. Any other queries used for specific metrics

Each query should be the EXACT query that was executed, so the user can run it in Power BI and verify the numbers match.

---

## GANTT CHART - MANDATORY IMPLEMENTATION

The Gantt chart MUST be included in EVERY report. Use this lightweight, pure CSS implementation (no JavaScript libraries):

### Gantt Structure (Pure CSS - No JS Libraries)
```html
<div class="section-label"><span>Project Timeline</span></div>
<div class="gantt-wrapper">
    <table class="gantt-table">
        <thead>
            <tr>
                <th class="gantt-task-col">Phase / Task</th>
                <th class="gantt-timeline-header" colspan="TOTAL_DAYS">
                    <div class="gantt-months">
                        <!-- Month headers spanning their days -->
                        <span style="grid-column: span 5;">Jan 2026</span>
                        <span style="grid-column: span 10;">Feb 2026</span>
                    </div>
                </th>
            </tr>
        </thead>
        <tbody>
            <!-- Phase Row -->
            <tr class="gantt-phase-row">
                <td class="gantt-task-cell">
                    <span class="phase-dot phase-1"></span>
                    <strong>Phase Name</strong>
                </td>
                <td class="gantt-timeline-cell" colspan="TOTAL_DAYS">
                    <div class="gantt-grid" style="--days: TOTAL_DAYS;">
                        <!-- Day grid lines rendered by CSS -->
                    </div>
                </td>
            </tr>
            <!-- Task Row -->
            <tr class="gantt-task-row">
                <td class="gantt-task-cell">
                    <span class="task-name">Task Name</span>
                    <span class="task-hours">8h</span>
                </td>
                <td class="gantt-timeline-cell" colspan="TOTAL_DAYS">
                    <div class="gantt-grid" style="--days: TOTAL_DAYS;">
                        <div class="gantt-bar phase-1" style="--start: 0; --duration: 3;">Task</div>
                    </div>
                </td>
            </tr>
        </tbody>
    </table>
</div>
```

### Gantt CSS (Lightweight, Pure CSS)
```css
/* Gantt Chart - Lightweight Pure CSS */
.gantt-wrapper {
    overflow-x: auto;
    margin-bottom: var(--space-2xl);
    border: 1px solid #E2E8F0;
    border-radius: 12px;
}

.gantt-table {
    width: 100%;
    min-width: 800px;
    border-collapse: collapse;
    table-layout: fixed;
}

.gantt-task-col {
    width: 200px;
    min-width: 200px;
    background: var(--navy-primary);
    color: white;
    padding: 12px 16px;
    text-align: left;
    font-family: 'Montserrat', sans-serif;
    font-size: 13px;
    font-weight: 600;
}

.gantt-timeline-header {
    background: var(--navy-primary);
    color: white;
    padding: 8px;
    vertical-align: top;
}

.gantt-months {
    display: grid;
    grid-auto-flow: column;
    text-align: center;
    font-size: 12px;
    font-weight: 600;
}

.gantt-task-cell {
    padding: 10px 16px;
    border-bottom: 1px solid #E2E8F0;
    background: white;
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
}

.gantt-phase-row .gantt-task-cell {
    background: var(--sky-background);
}

.gantt-timeline-cell {
    padding: 0;
    border-bottom: 1px solid #E2E8F0;
    position: relative;
    height: 44px;
}

.gantt-grid {
    display: grid;
    grid-template-columns: repeat(var(--days), 1fr);
    height: 100%;
    position: relative;
    background: repeating-linear-gradient(
        90deg,
        transparent,
        transparent calc(100% / var(--days) - 1px),
        #E2E8F0 calc(100% / var(--days) - 1px),
        #E2E8F0 calc(100% / var(--days))
    );
}

.gantt-bar {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    height: 24px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    /* Position using CSS custom properties */
    left: calc((var(--start) / var(--days)) * 100%);
    width: calc((var(--duration) / var(--days)) * 100%);
    min-width: 40px;
}

.gantt-bar.phase-1 { background: linear-gradient(135deg, #8B5CF6, #7C3AED); }
.gantt-bar.phase-2 { background: linear-gradient(135deg, #2563EB, #1B365D); }
.gantt-bar.phase-3 { background: linear-gradient(135deg, #10B981, #059669); }
.gantt-bar.phase-4 { background: linear-gradient(135deg, #F59E0B, #D97706); }
.gantt-bar.phase-5 { background: linear-gradient(135deg, #EF4444, #DC2626); }
.gantt-bar.phase-6 { background: linear-gradient(135deg, #06B6D4, #0891B2); }

.phase-dot {
    width: 10px;
    height: 10px;
    border-radius: 3px;
    flex-shrink: 0;
}
.phase-dot.phase-1 { background: #8B5CF6; }
.phase-dot.phase-2 { background: #2563EB; }
.phase-dot.phase-3 { background: #10B981; }
.phase-dot.phase-4 { background: #F59E0B; }
.phase-dot.phase-5 { background: #EF4444; }
.phase-dot.phase-6 { background: #06B6D4; }

.task-name {
    flex: 1;
    font-size: 13px;
    color: var(--navy-primary);
}

.task-hours {
    font-size: 11px;
    font-weight: 600;
    color: #64748B;
    background: #F1F5F9;
    padding: 2px 8px;
    border-radius: 4px;
}

/* Print styles for Gantt */
@media print {
    .gantt-wrapper { overflow: visible; }
    .gantt-table { min-width: 0; }
    .gantt-bar { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
```

### Gantt Bar Positioning
Calculate bar position using these CSS custom properties:
- `--days`: Total number of days in the timeline
- `--start`: Day index where the task starts (0-based from timeline start)
- `--duration`: Number of days the task spans

Example for a task starting day 3 and lasting 5 days over a 20-day timeline:
```html
<div class="gantt-bar phase-1" style="--start: 3; --duration: 5;">Task Name</div>
```
The parent `.gantt-grid` must have `style="--days: 20;"`.

---

## PDF Export - LIGHTWEIGHT APPROACH

**DO NOT use html2pdf.js** - it loads html2canvas which consumes 500MB+ RAM.

**Use native browser print instead:**

```html
<!-- Export button in header -->
<button class="export-btn" onclick="window.print()">Export as PDF</button>
```

```css
/* Print styles */
@media print {
    * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }

    body { background: white; }

    .export-bar, .export-btn { display: none !important; }
    .internal-banner { display: none !important; }

    .page-wrapper { padding: 0; }

    .page {
        box-shadow: none;
        border-radius: 0;
        padding: 15mm;
        max-width: none;
    }

    /* Preserve colors */
    .title-section,
    .gantt-task-col,
    .gantt-timeline-header,
    .phase-table th,
    .metric-card.highlight,
    .status-badge,
    .gantt-bar {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }

    /* Page breaks */
    .gantt-wrapper { page-break-inside: avoid; }
    .summary-section { page-break-inside: avoid; }
    .table-container { page-break-inside: avoid; }

    /* Remove hover effects */
    .metric-card:hover {
        transform: none;
        box-shadow: none;
    }
}
```

**User instruction:** When exporting, use browser's "Save as PDF" option in the print dialog. Zero external libraries, better quality output, works offline.

---

## COMPLETE CSS FRAMEWORK

Include ALL of the following CSS in both reports. The CSS uses custom properties for easy rebranding.

```css
/* === IMPORTS === */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Montserrat:wght@600;700;800&display=swap');

/* === CSS CUSTOM PROPERTIES === */
:root {
    /* Primary branding - override these for custom branding */
    --navy-primary: #1B365D;
    --brand-blue: #164487;
    --navy-dark: #002C60;
    --blue-bright: #2563EB;
    --blue-light: #60A5FA;
    --green-cta: #00D9A5;
    --sky-background: #E8F4FD;

    /* Functional colors - do NOT override */
    --green-success: #10B981;
    --amber-warning: #F59E0B;
    --red-danger: #EF4444;
    --internal-red: #DC2626;
    --internal-red-light: #FEE2E2;

    /* Neutrals */
    --white: #FFFFFF;
    --gray-50: #F8FAFC;
    --gray-100: #F1F5F9;
    --gray-200: #E2E8F0;
    --gray-400: #94A3B8;
    --gray-600: #475569;
    --gray-800: #1E293B;

    /* Spacing (8px base) */
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    --space-xl: 32px;
    --space-2xl: 48px;
}

/* === BASE STYLES === */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--gray-50);
    color: var(--gray-600);
    line-height: 1.6;
    font-size: 14px;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Montserrat', sans-serif;
    color: var(--navy-primary);
    line-height: 1.3;
}

/* === LAYOUT === */
.page-wrapper {
    max-width: 1100px;
    margin: 0 auto;
    padding: 80px var(--space-xl) var(--space-2xl);
}

/* Internal report needs more top padding for banner */
.page-wrapper.internal {
    padding-top: 112px;
}

.page {
    background: white;
    border-radius: 16px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    padding: var(--space-2xl);
}

/* === EXPORT BAR === */
.export-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    background: var(--navy-primary);
    padding: var(--space-md) var(--space-xl);
    display: flex;
    justify-content: space-between;
    align-items: center;
    z-index: 1000;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
}

/* Internal: export bar sits below the banner */
.internal-report .export-bar {
    top: 32px;
}

.export-bar-title {
    font-family: 'Montserrat', sans-serif;
    color: var(--white);
    font-size: 14px;
    font-weight: 600;
}

.export-btn {
    background: linear-gradient(135deg, var(--green-cta), #00B386);
    color: var(--white);
    border: none;
    padding: 12px 28px;
    border-radius: 8px;
    font-family: 'Montserrat', sans-serif;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(0, 217, 165, 0.3);
}

.export-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0, 217, 165, 0.4);
}

/* === INTERNAL BANNER === */
.internal-banner {
    background: var(--internal-red);
    color: white;
    text-align: center;
    padding: 8px;
    font-family: 'Montserrat', sans-serif;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 2px;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1001;
}

.confidential-label {
    background: var(--internal-red-light);
    color: var(--internal-red);
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    margin-left: 12px;
}

/* === HEADER === */
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: var(--space-lg);
    border-bottom: 3px solid var(--brand-blue);
    margin-bottom: var(--space-2xl);
}

.internal-report .header {
    border-bottom-color: var(--internal-red);
}

.logo-container {
    display: flex;
    align-items: center;
}

.logo-container img,
.logo-container svg {
    height: 48px;
    width: auto;
}

.logo-placeholder {
    font-family: 'Montserrat', sans-serif;
    font-size: 24px;
    font-weight: 800;
    color: var(--navy-primary);
    letter-spacing: -0.5px;
}

.header-meta {
    text-align: right;
    font-size: 13px;
    color: var(--gray-600);
    line-height: 1.8;
}

.header-meta strong {
    color: var(--navy-primary);
    font-weight: 600;
}

/* === TITLE SECTION === */
.title-section {
    background: linear-gradient(135deg, var(--navy-primary) 0%, var(--navy-dark) 100%);
    border-radius: 16px;
    padding: var(--space-2xl);
    margin-bottom: var(--space-2xl);
    color: white;
    position: relative;
    overflow: hidden;
}

.title-section::after {
    content: '';
    position: absolute;
    top: -30%;
    right: -5%;
    width: 200px;
    height: 200px;
    background: var(--green-cta);
    border-radius: 50%;
    opacity: 0.08;
}

.title-section h1 {
    color: white;
    font-size: 28px;
    font-weight: 800;
    margin-bottom: var(--space-sm);
}

.title-section .client-name {
    color: var(--green-cta);
    font-size: 16px;
    font-weight: 600;
    margin-bottom: var(--space-lg);
}

.status-badge {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

.status-badge.active { background: rgba(16, 185, 129, 0.2); color: #6EE7B7; }
.status-badge.complete { background: rgba(96, 165, 250, 0.2); color: #93C5FD; }
.status-badge.at-risk { background: rgba(245, 158, 11, 0.2); color: #FCD34D; }

.title-details {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-md);
    margin-top: var(--space-lg);
}

.title-details .detail-item {
    font-size: 13px;
}

.title-details .detail-label {
    color: rgba(255, 255, 255, 0.6);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.title-details .detail-value {
    color: white;
    font-weight: 600;
}

/* === SECTION LABELS === */
.section-label {
    margin: var(--space-2xl) 0 var(--space-lg);
}

.section-label span {
    font-family: 'Montserrat', sans-serif;
    font-size: 18px;
    font-weight: 700;
    color: var(--navy-primary);
    padding-bottom: var(--space-sm);
    border-bottom: 3px solid var(--green-cta);
}

/* === METRIC CARDS === */
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-2xl);
}

.metric-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: var(--space-lg);
    transition: transform 0.2s, box-shadow 0.2s;
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
}

.metric-card.highlight {
    background: linear-gradient(135deg, var(--navy-primary), var(--brand-blue));
    color: white;
    border: none;
}

.metric-card.highlight .metric-label,
.metric-card.highlight .metric-sub {
    color: rgba(255, 255, 255, 0.7);
}

.metric-card.highlight .metric-value {
    color: white;
}

.metric-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--gray-400);
    margin-bottom: var(--space-xs);
    font-weight: 600;
}

.metric-value {
    font-family: 'Montserrat', sans-serif;
    font-size: 32px;
    font-weight: 800;
    color: var(--navy-primary);
    line-height: 1;
    margin-bottom: var(--space-xs);
}

.metric-sub {
    font-size: 12px;
    color: var(--gray-400);
}

.progress-bar-container {
    height: 6px;
    background: var(--gray-200);
    border-radius: 3px;
    margin-top: var(--space-sm);
    overflow: hidden;
}

.progress-bar-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--green-cta);
    transition: width 0.5s ease;
}

.metric-card.highlight .progress-bar-container {
    background: rgba(255, 255, 255, 0.2);
}

.metric-card.highlight .progress-bar-fill {
    background: var(--green-cta);
}

/* === KEY DELIVERABLES === */
.deliverables-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-2xl);
}

.deliverable-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: var(--space-lg);
    display: flex;
    gap: var(--space-md);
    align-items: flex-start;
}

.deliverable-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
}

.deliverable-icon.complete { background: #D1FAE5; }
.deliverable-icon.in-progress { background: #DBEAFE; }

.deliverable-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--navy-primary);
    margin-bottom: 4px;
}

.deliverable-desc {
    font-size: 13px;
    color: var(--gray-600);
}

/* === TABLES === */
.table-container {
    overflow-x: auto;
    margin-bottom: var(--space-2xl);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

thead th {
    background: var(--navy-primary);
    color: white;
    padding: 12px 16px;
    text-align: left;
    font-family: 'Montserrat', sans-serif;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

tbody td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--gray-200);
    font-size: 13px;
}

tbody tr:nth-child(even) {
    background: var(--gray-50);
}

tbody tr:hover {
    background: var(--sky-background);
}

/* Status pills */
.pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

.pill.complete { background: #D1FAE5; color: #065F46; }
.pill.in-progress { background: #DBEAFE; color: #1E40AF; }
.pill.planned { background: #FEF3C7; color: #92400E; }
.pill.at-risk { background: #FEE2E2; color: #991B1B; }
.pill.on-track { background: #D1FAE5; color: #065F46; }
.pill.over-budget { background: #FEE2E2; color: #991B1B; }
.pill.warning { background: #FEF3C7; color: #92400E; }

/* === BUDGET BAR CHART === */
.budget-bars {
    margin-bottom: var(--space-2xl);
}

.budget-bar-row {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-md);
    gap: var(--space-md);
}

.budget-bar-label {
    width: 140px;
    min-width: 140px;
    font-size: 13px;
    font-weight: 600;
    color: var(--navy-primary);
    text-align: right;
}

.budget-bar-track {
    flex: 1;
    height: 28px;
    background: var(--gray-100);
    border-radius: 6px;
    position: relative;
    overflow: hidden;
}

.budget-bar-fill {
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 12px;
    font-size: 11px;
    font-weight: 600;
    color: white;
    transition: width 0.5s ease;
}

.budget-bar-fill.ok { background: linear-gradient(135deg, #10B981, #059669); }
.budget-bar-fill.warn { background: linear-gradient(135deg, #F59E0B, #D97706); }
.budget-bar-fill.over { background: linear-gradient(135deg, #EF4444, #DC2626); }

.budget-bar-budget-mark {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--navy-primary);
}

.budget-bar-value {
    width: 80px;
    min-width: 80px;
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-600);
}

/* === MANAGEMENT SUMMARY === */
.summary-section {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: var(--space-2xl);
    margin-bottom: var(--space-2xl);
}

.summary-section p {
    margin-bottom: var(--space-md);
    line-height: 1.8;
}

.summary-section p:last-child {
    margin-bottom: 0;
}

/* === CHECKLISTS === */
.checklist {
    list-style: none;
    margin-bottom: var(--space-2xl);
}

.checklist li {
    padding: var(--space-sm) 0;
    border-bottom: 1px solid var(--gray-100);
    display: flex;
    align-items: flex-start;
    gap: var(--space-sm);
    font-size: 13px;
}

.checklist .check-icon {
    color: var(--green-success);
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 2px;
}

.checklist .circle-icon {
    color: var(--blue-bright);
    flex-shrink: 0;
    margin-top: 2px;
}

/* === RISK TABLE === */
.risk-table .impact-high { color: var(--red-danger); font-weight: 600; }
.risk-table .impact-medium { color: var(--amber-warning); font-weight: 600; }
.risk-table .impact-low { color: var(--green-success); font-weight: 600; }

/* === DECISION POINTS === */
.decisions-list {
    margin-bottom: var(--space-2xl);
}

.decision-item {
    display: flex;
    gap: var(--space-md);
    padding: var(--space-md) 0;
    border-bottom: 1px solid var(--gray-100);
}

.decision-number {
    width: 32px;
    height: 32px;
    min-width: 32px;
    background: var(--navy-primary);
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Montserrat', sans-serif;
    font-weight: 700;
    font-size: 13px;
}

.decision-content {
    flex: 1;
}

.decision-title {
    font-weight: 600;
    color: var(--navy-primary);
    margin-bottom: 4px;
}

.decision-date {
    display: inline-block;
    background: var(--sky-background);
    color: var(--brand-blue);
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    margin-top: 4px;
}

/* === FINDINGS CARDS === */
.findings-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-2xl);
}

.finding-card {
    border-radius: 12px;
    padding: var(--space-lg);
    border-left: 4px solid;
}

.finding-card.success {
    background: #F0FDF4;
    border-color: var(--green-success);
}

.finding-card.warning {
    background: #FFFBEB;
    border-color: var(--amber-warning);
}

.finding-card.info {
    background: #EFF6FF;
    border-color: var(--blue-bright);
}

.finding-card.danger {
    background: #FEF2F2;
    border-color: var(--red-danger);
}

.finding-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--navy-primary);
    margin-bottom: var(--space-xs);
}

.finding-text {
    font-size: 13px;
    color: var(--gray-600);
}

/* === INTERNAL-ONLY SECTIONS === */

/* Financial Overview Cards */
.financial-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-2xl);
}

.financial-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: var(--space-lg);
    border-top: 4px solid var(--brand-blue);
}

.financial-card.profit-high { border-top-color: var(--green-success); }
.financial-card.profit-mid { border-top-color: var(--amber-warning); }
.financial-card.profit-low { border-top-color: var(--red-danger); }

/* Traffic Light Indicators */
.traffic-lights {
    display: flex;
    gap: var(--space-xl);
    margin-bottom: var(--space-2xl);
    justify-content: center;
}

.traffic-light {
    text-align: center;
}

.traffic-light .indicator {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    margin: 0 auto var(--space-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
}

.indicator.green { background: #D1FAE5; color: #065F46; }
.indicator.amber { background: #FEF3C7; color: #92400E; }
.indicator.red { background: #FEE2E2; color: #991B1B; }

.traffic-light .indicator-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--navy-primary);
}

/* Lessons Learned */
.lessons-section {
    margin-bottom: var(--space-2xl);
}

.lessons-category {
    margin-bottom: var(--space-lg);
}

.lessons-category h4 {
    font-size: 14px;
    margin-bottom: var(--space-sm);
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}

.lessons-category h4 .icon-success { color: var(--green-success); }
.lessons-category h4 .icon-warning { color: var(--amber-warning); }
.lessons-category h4 .icon-info { color: var(--blue-bright); }

.lessons-category ul {
    list-style: none;
    padding-left: var(--space-lg);
}

.lessons-category li {
    padding: var(--space-xs) 0;
    font-size: 13px;
    position: relative;
}

.lessons-category li::before {
    content: '>';
    position: absolute;
    left: -16px;
    color: var(--gray-400);
    font-weight: 600;
}

/* === FOOTER === */
.footer {
    margin-top: 64px;
    padding-top: var(--space-lg);
    border-top: 2px solid var(--brand-blue);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.internal-report .footer {
    border-top-color: var(--internal-red);
}

.footer-logo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-xs);
}

.footer-tagline {
    font-family: 'Montserrat', sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: var(--brand-blue);
    font-style: italic;
}

.footer-confidential {
    font-family: 'Montserrat', sans-serif;
    font-size: 11px;
    font-weight: 700;
    color: var(--internal-red);
    letter-spacing: 1px;
}

.footer-info {
    text-align: right;
    font-size: 12px;
    color: var(--gray-600);
    line-height: 1.8;
}

.footer-info a {
    color: var(--blue-bright);
    text-decoration: none;
    font-weight: 500;
}

/* === RESPONSIVE === */
@media (max-width: 768px) {
    .metrics-grid,
    .financial-grid { grid-template-columns: repeat(2, 1fr); }
    .deliverables-grid,
    .findings-grid { grid-template-columns: 1fr; }
    .title-details { grid-template-columns: 1fr; }
    .traffic-lights { flex-direction: column; align-items: center; }
}
```

---

## EXTERNAL REPORT HTML STRUCTURE

Use this as the skeleton for the external report. Replace bracketed values with actual data.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[Anonymized Project Name] - Project Status Report</title>
    <style>
        /* === PASTE FULL CSS FRAMEWORK HERE === */
    </style>
</head>
<body>
    <!-- Export Bar -->
    <div class="export-bar">
        <div class="export-bar-title">Project Status Report Preview</div>
        <button class="export-btn" onclick="window.print()">Export as PDF</button>
    </div>

    <div class="page-wrapper">
        <div class="page">
            <!-- Header -->
            <header class="header">
                <div class="logo-container">
                    <!-- Replace with your logo SVG/img, or use text placeholder -->
                    <span class="logo-placeholder">YOUR COMPANY</span>
                </div>
                <div class="header-meta">
                    <div><strong>Report Date:</strong> [CURRENT DATE]</div>
                    <div><strong>Document:</strong> RPT-[YEAR]-[MONTH]-[PROJECT_ID]</div>
                    <div><strong>Period:</strong> [START DATE] - [END DATE or Present]</div>
                </div>
            </header>

            <!-- Title Section -->
            <div class="title-section">
                <h1>[Anonymized Project Name]</h1>
                <div class="client-name">[Anonymized Client Name]</div>
                <span class="status-badge active">In Progress</span>
                <div class="title-details">
                    <div class="detail-item">
                        <div class="detail-label">Project Number</div>
                        <div class="detail-value">[ID]</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Project Manager</div>
                        <div class="detail-value">[Anonymized PM Name]</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Contact</div>
                        <div class="detail-value">[Anonymized Contact]</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Target Date</div>
                        <div class="detail-value">[Date]</div>
                    </div>
                </div>
            </div>

            <!-- Metric Cards -->
            <div class="section-label"><span>Key Metrics</span></div>
            <div class="metrics-grid">
                <div class="metric-card highlight">
                    <div class="metric-label">Progress</div>
                    <div class="metric-value">[XX]%</div>
                    <div class="metric-sub">[X] of [Y] tasks complete</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: [XX]%"></div>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Hours Used</div>
                    <div class="metric-value">[XX]h</div>
                    <div class="metric-sub">[XX]h of [XX]h budget</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: [XX]%"></div>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Duration</div>
                    <div class="metric-value">[XX]</div>
                    <div class="metric-sub">days elapsed</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Open Risks</div>
                    <div class="metric-value">[X]</div>
                    <div class="metric-sub">[X] high, [X] medium</div>
                </div>
            </div>

            <!-- Key Deliverables -->
            <div class="section-label"><span>Key Deliverables</span></div>
            <div class="deliverables-grid">
                <!-- Repeat for each deliverable -->
                <div class="deliverable-card">
                    <div class="deliverable-icon complete">&#10003;</div>
                    <div>
                        <div class="deliverable-title">[Deliverable Name]</div>
                        <div class="deliverable-desc">[Description]</div>
                    </div>
                </div>
            </div>

            <!-- Gantt Chart - MANDATORY -->
            <!-- See GANTT CHART section above for full implementation -->

            <!-- Phase Summary Table -->
            <div class="section-label"><span>Phase Summary</span></div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Phase</th>
                            <th>Status</th>
                            <th>Budget (h)</th>
                            <th>Spent (h)</th>
                            <th>Remaining (h)</th>
                            <th>% Used</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Repeat for each phase -->
                        <tr>
                            <td><strong>[Phase Name]</strong></td>
                            <td><span class="pill on-track">On Track</span></td>
                            <td>[XX]</td>
                            <td>[XX]</td>
                            <td>[XX]</td>
                            <td>[XX]%</td>
                        </tr>
                    </tbody>
                    <tfoot>
                        <tr style="font-weight: 700; background: var(--sky-background);">
                            <td>Total</td>
                            <td></td>
                            <td>[XX]</td>
                            <td>[XX]</td>
                            <td>[XX]</td>
                            <td>[XX]%</td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <!-- Budget Bar Chart -->
            <div class="section-label"><span>Budget by Phase</span></div>
            <div class="budget-bars">
                <!-- Repeat for each phase -->
                <div class="budget-bar-row">
                    <div class="budget-bar-label">[Phase]</div>
                    <div class="budget-bar-track">
                        <div class="budget-bar-fill ok" style="width: [XX]%">[XX]h</div>
                        <div class="budget-bar-budget-mark" style="left: 100%"></div>
                    </div>
                    <div class="budget-bar-value">[XX]h / [XX]h</div>
                </div>
            </div>

            <!-- Management Summary -->
            <div class="section-label"><span>Management Summary</span></div>
            <div class="summary-section">
                <p>[Summary paragraph 1]</p>
                <p>[Summary paragraph 2]</p>
            </div>

            <!-- Resource Overview -->
            <div class="section-label"><span>Resource Overview</span></div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Resource</th>
                            <th>Role</th>
                            <th>This Period</th>
                            <th>Total Spent</th>
                            <th>Budget</th>
                            <th>Available</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Anonymized names -->
                    </tbody>
                </table>
            </div>

            <!-- Completed Work -->
            <div class="section-label"><span>Completed Work</span></div>
            <ul class="checklist">
                <li><span class="check-icon">&#10003;</span> [Completed task description]</li>
            </ul>

            <!-- Planned Work -->
            <div class="section-label"><span>Planned Work</span></div>
            <ul class="checklist">
                <li><span class="circle-icon">&#9675;</span> [Planned task description]</li>
            </ul>

            <!-- Risks & Issues -->
            <div class="section-label"><span>Risks &amp; Issues</span></div>
            <div class="table-container">
                <table class="risk-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Risk</th>
                            <th>Impact</th>
                            <th>Likelihood</th>
                            <th>Status</th>
                            <th>Mitigation</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Repeat -->
                    </tbody>
                </table>
            </div>

            <!-- Decision Points -->
            <div class="section-label"><span>Decision Points</span></div>
            <div class="decisions-list">
                <div class="decision-item">
                    <div class="decision-number">1</div>
                    <div class="decision-content">
                        <div class="decision-title">[Decision description]</div>
                        <span class="decision-date">Deadline: [Date]</span>
                    </div>
                </div>
            </div>

            <!-- Findings -->
            <div class="section-label"><span>Findings</span></div>
            <div class="findings-grid">
                <div class="finding-card success">
                    <div class="finding-title">[Finding title]</div>
                    <div class="finding-text">[Finding description]</div>
                </div>
                <div class="finding-card warning">
                    <div class="finding-title">[Finding title]</div>
                    <div class="finding-text">[Finding description]</div>
                </div>
            </div>

            <!-- Footer -->
            <footer class="footer">
                <div class="footer-logo">
                    <span class="logo-placeholder">YOUR COMPANY</span>
                    <div class="footer-tagline">Your tagline here</div>
                </div>
                <div class="footer-info">
                    <div>Generated with Power BI MCP</div>
                    <div><a href="#">www.yourcompany.com</a></div>
                    <div>&copy; [YEAR] Your Company. All rights reserved.</div>
                </div>
            </footer>
        </div>
    </div>

    <script>
        function copyDAX(btn) {
            const code = btn.parentElement.querySelector('code').textContent;
            navigator.clipboard.writeText(code).then(() => {
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = 'Copy Query'; }, 2000);
            });
        }
    </script>
</body>
</html>
```

---

## INTERNAL REPORT HTML STRUCTURE

The internal report uses the same skeleton as the external report, with these additions:

```html
<body class="internal-report">
    <!-- Internal Banner (FIRST element) -->
    <div class="internal-banner">INTERNAL USE ONLY - CONFIDENTIAL</div>

    <!-- Export Bar (below banner) -->
    <div class="export-bar">
        <div class="export-bar-title">
            Internal Project Report
            <span class="confidential-label">CONFIDENTIAL - INTERNAL</span>
        </div>
        <button class="export-btn" onclick="window.print()">Export as PDF</button>
    </div>

    <div class="page-wrapper internal">
        <div class="page">
            <!-- Header (with red border via .internal-report .header) -->
            <!-- ... same header structure, document prefix INT- instead of RPT- ... -->

            <!-- ALL external report sections go here -->

            <!-- THEN add internal-only sections: -->

            <!-- Financial Overview -->
            <div class="section-label"><span>Financial Overview</span></div>
            <div class="financial-grid">
                <div class="financial-card">
                    <div class="metric-label">Revenue</div>
                    <div class="metric-value">$[XX,XXX]</div>
                </div>
                <div class="financial-card">
                    <div class="metric-label">Cost</div>
                    <div class="metric-value">$[XX,XXX]</div>
                </div>
                <div class="financial-card profit-high">
                    <div class="metric-label">Profit</div>
                    <div class="metric-value">$[XX,XXX]</div>
                </div>
                <div class="financial-card profit-high">
                    <div class="metric-label">Margin</div>
                    <div class="metric-value">[XX]%</div>
                </div>
            </div>

            <!-- Budget Analysis -->
            <div class="section-label"><span>Budget Analysis</span></div>
            <div class="financial-grid">
                <div class="financial-card">
                    <div class="metric-label">Budgeted Hours</div>
                    <div class="metric-value">[XXX]h</div>
                </div>
                <div class="financial-card">
                    <div class="metric-label">Actual Hours</div>
                    <div class="metric-value">[XXX]h</div>
                </div>
                <div class="financial-card">
                    <div class="metric-label">Variance</div>
                    <div class="metric-value">[+/-XX]h</div>
                </div>
                <div class="financial-card">
                    <div class="metric-label">Efficiency</div>
                    <div class="metric-value">[XX]%</div>
                </div>
            </div>

            <!-- Performance Indicators -->
            <div class="section-label"><span>Performance Indicators</span></div>
            <div class="traffic-lights">
                <div class="traffic-light">
                    <div class="indicator green">&#10003;</div>
                    <div class="indicator-label">Schedule</div>
                </div>
                <div class="traffic-light">
                    <div class="indicator amber">!</div>
                    <div class="indicator-label">Budget</div>
                </div>
                <div class="traffic-light">
                    <div class="indicator green">&#10003;</div>
                    <div class="indicator-label">Margin</div>
                </div>
            </div>

            <!-- Resource Utilization (with costs) -->
            <div class="section-label"><span>Resource Utilization</span></div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Team Member</th>
                            <th>Role</th>
                            <th>Hours</th>
                            <th>Est. Cost</th>
                            <th>% of Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Anonymized names with cost data -->
                    </tbody>
                </table>
            </div>

            <!-- Lessons Learned -->
            <div class="section-label"><span>Lessons Learned</span></div>
            <div class="lessons-section">
                <div class="lessons-category">
                    <h4><span class="icon-success">&#10003;</span> What Went Well</h4>
                    <ul>
                        <li>[Item]</li>
                    </ul>
                </div>
                <div class="lessons-category">
                    <h4><span class="icon-warning">&#9888;</span> Areas for Improvement</h4>
                    <ul>
                        <li>[Item]</li>
                    </ul>
                </div>
                <div class="lessons-category">
                    <h4><span class="icon-info">&#10132;</span> Recommendations for Similar Projects</h4>
                    <ul>
                        <li>[Item]</li>
                    </ul>
                </div>
            </div>

            <!-- DAX Verification Section - MANDATORY -->
            <!-- See DAX VERIFICATION SECTION above for full implementation -->

            <!-- Footer with confidential label -->
            <footer class="footer">
                <div class="footer-logo">
                    <span class="logo-placeholder">YOUR COMPANY</span>
                    <div class="footer-confidential">CONFIDENTIAL - INTERNAL USE ONLY</div>
                </div>
                <div class="footer-info">
                    <div>Generated with Power BI MCP</div>
                    <div><a href="#">www.yourcompany.com</a></div>
                    <div>&copy; [YEAR] Your Company. All rights reserved.</div>
                </div>
            </footer>
        </div>
    </div>

    <script>
        function copyDAX(btn) {
            const code = btn.parentElement.querySelector('code').textContent;
            navigator.clipboard.writeText(code).then(() => {
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = 'Copy Query'; }, 2000);
            });
        }
    </script>
</body>
```

---

## OUTPUT

After generating both reports:
1. Write External HTML to `./Project_[ProjectName]_Report.html` (user's working directory)
2. Write Internal HTML to `./INTERNAL_Project_[ProjectName]_Report.html` (user's working directory)
3. Open BOTH files in browser: `open [external].html && open [internal].html`
4. Tell the user:
   - External report is ready to share with the client
   - Internal report contains confidential financial data, do not share externally
   - Use Cmd+P (or Ctrl+P) and "Save as PDF" to export

**Console Output Privacy (demo mode only):**
- When generating demo/showcase reports with anonymization enabled: NEVER mention original names in your output messages
- Do NOT show name mappings in your response
- When generating real reports (default): use real names in your summary as they appear in the reports
