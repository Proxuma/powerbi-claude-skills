# QBR Report Generator

Generate a client-ready Quarterly Business Review from your Power BI data. The output is a
single self-contained HTML file with a floating **Export as PDF** button, plus a rendered PDF.

**Customer:** $ARGUMENTS

> If no customer is given, ask once which customer (and, if unclear, which quarter).
> Otherwise ask nothing else — produce the report straight away.

---

## What this produces

A polished, board-ready QBR in the **"Clear Perspective"** design: a cover, a six-number
summary, an 8-dimension maturity benchmark, service delivery, Microsoft 365, cybersecurity,
RMM/endpoint, hardware lifecycle, contracts, risks & opportunities, and a prioritized action
list — each data section carrying a collapsible DAX proof panel showing exactly what was
queried.

**The design is fixed by default.** `templates/qbr-template.html` is the source of truth: its
CSS, its count-up / reveal / bar-fill JS, its print rules and its PDF button are copied
**verbatim**. You only fill in data and, optionally, re-skin the brand tokens (see Step 1).

---

## Step 0 — Data comes pre-anonymized. Do not anonymize anything yourself.

The MCP server anonymizes every response before it reaches you. You will see aliases like
`Client_A`, `Resource_1`, `Contact_3` — never real names. **This is by design. Do not add,
remove, or second-guess anonymization, and do not write "anonymize this" instructions into the
report.** Build the report with whatever values the MCP returns.

Real names are restored **locally, after generation**, by the deanonymizer — the mapping never
leaves the user's machine (see Step 5). So: query freely, build the report, hand off. The
round trip (anonymize on the way out, de-anonymize on the way back) is the MCP's job, not
yours.

The one exception: the **subject company's own name** in the report title and cover is expected
and fine — the user is presenting to that client. Never expose *other* clients' data.

One formatting rule: if an alias contains angle brackets (Presidio Pass 2 produces aliases like
`<PERSON_1>`), write it HTML-escaped in the report HTML: `&lt;PERSON_1&gt;`. A raw `<PERSON_1>`
is parsed by browsers as an unknown tag and renders as nothing. Both restore paths still match
the escaped form.

---

## Step 1 — Styling: default look, or match the customer's brand

**Default (the user says nothing about styling):** use `templates/qbr-template.html` as-is.
Fill `{{MSP_NAME}}` with the MSP's own name (from setup or ask once); leave the palette,
fonts and layout untouched. This is the intended look.

**If the user gives a website or brand** (e.g. "make it match acme-it.com", "use our brand",
"here's our logo"): adapt the template's brand layer to that identity, keeping the structure
and every component class identical. Only these things change:

1. **Fetch the site.** Read the homepage. Pull the primary brand color, a secondary/accent
   color, and the heading + body typefaces. Prefer values from CSS variables, the logo, and
   buttons over incidental colors.
2. **Re-skin the brand tokens only.** Edit the `:root` block at the very top of the template
   (the block marked *BRAND TOKENS*): set `--brand`, `--brand-hover`, `--accent` and rebuild
   `--grad` from those. If the brand fonts differ, swap the Google Fonts `<link>` and
   `--sans` / `--mono`. Touch nothing below that block — the whole report re-colors from those
   variables.
3. **Logo, calibrated to the background.** Download the customer's logo (SVG preferred, else
   the highest-resolution PNG). Embed it as a data URI in the header:
   `<span class="logo"><img src="data:image/...;base64,..." alt="MSP name"></span>`. The header
   is light (`rgba(255,255,255,.82)`) — if the logo is a light/white knockout that would vanish
   on white, use the dark/full-color variant, or the version the site itself uses on a light
   header. Check the contrast; never ship a logo that disappears into its background. If only a
   light logo exists, place it on the dark `.band` sections instead and keep a text wordmark in
   the light header.
4. **Keep readability honest.** If a brand color is too light for text or fills, darken it for
   text use (keep the bright value for accents/marks). The status colors (green/amber/red) stay
   as-is — they encode meaning, not brand.

Do **not** redesign the layout, move sections, or change the component set. Re-skin only.

---

## Step 2 — Discover the workspace, dataset and data model

Do not hardcode workspace or dataset IDs.

1. `list_workspaces()` → if more than one, ask which holds the PSA/RMM data.
2. `list_datasets(workspace_id=...)` → if more than one, ask which to use. Store `dataset_id`.
3. Map the model before writing DAX. **Never call `get_schema`** (it can exceed 10MB and crash
   the session). Use `search_schema` with specific terms and `list_measures`:

```
search_schema(... search_term="company")      list_measures(...)
search_schema(... search_term="ticket")        search_schema(... search_term="sla")
search_schema(... search_term="contract")      search_schema(... search_term="configuration")
search_schema(... search_term="license")       search_schema(... search_term="warranty")
```

Every dataset names things differently (Autotask, ConnectWise, HaloPSA, Datto RMM). Build a
mental map of: the company table + name/id columns, the ticket table + category/priority/
status/SLA columns, configuration items / assets + warranty + active flag, and contracts +
type + status. Confirm real column and measure names before querying — never invent DAX.

---

## Step 3 — Pull the data, section by section

Query per section and cap every result (`TOPN`, filters) to stay memory-safe. Find the
company id first, then filter every query to it:

```dax
EVALUATE FILTER('<CompanyTable>', SEARCH("<CUSTOMER>", '<CompanyTable>'[<name_col>], 1, 0) > 0)
```

| Section | Source | Notes |
|---|---|---|
| Summary (6 numbers) | Derived from the sections below | pick the six that matter most for this client |
| Golden Standard (8 dims) | Derived per dimension, 1–10 | score from the real data you pulled |
| Service delivery | PSA — real | tickets, SLA %, categories, trends vs prior quarter |
| Microsoft 365 | M365 / adviser | license counts, adoption; assessment where no data |
| Cybersecurity | Secure Score / assessment | MFA, email auth, endpoint, dark web |
| RMM & endpoint | RMM — real if present | patch %, OS split, device health |
| Hardware lifecycle | CI/asset data — real | age, warranty, replacement plan |
| Contracts & licenses | PSA — real | active contracts, renewals, upsell |
| Risks & opportunities | Synthesized from above | the sharpest 4 risks + 3 opportunities |
| Recommended actions | Synthesized from above | prioritized, with investment + impact |

PSA/RMM figures come from Power BI. M365 posture, Secure Score, dark web and hardware age
often are **not** in the dataset — take them from the adviser's input or leave sensible
assessment defaults and **keep the demo pill** until every section is backed by real data.

**No internal financials in a client-facing QBR.** Revenue, cost, margin and hours
worked/billed are MSP-internal — the client sees your margin and questions your pricing.
Replace any financial KPI with a client-relevant metric (license utilization, AV coverage,
devices managed). These measures may exist in the dataset; never put them in the report.

**Patching tone.** Always include patch data, but frame it as proactive monitoring with a
remediation plan. The MSP is responsible for patching, so "backlog / hygiene / vulnerable"
blames the MSP in front of its own client. Break it down (approved-pending, install-error,
reboot-required, no-policy), state what is already scheduled, and show the path to target. Use
"needs attention" not "critical failure"; "accelerate" and "next step" not "backlog".

---

## Step 4 — Build the report from the template

1. Read `templates/qbr-template.html`. Copy its CSS, JS and structure **verbatim**. Never
   restyle (except the brand-token re-skin in Step 1 when requested).
2. Fill the header placeholders: `{{MSP_NAME}}`, `{{COMPANY}}`, `{{PERIOD}}`, `{{PERIOD_SHORT}}`,
   `{{PREV_PERIOD_SHORT}}`, `{{NEXT_PERIOD_SHORT}}`, `{{ADVISER}}`, `{{USERS}}`, `{{DEVICES}}`,
   `{{LOCATION}}`.
3. Replace the demo numbers, table rows, bar widths, scores, pill colors and prose with the
   client's real values. Keep every class, `data-w`, `data-count`, `data-dec`,
   `data-prefix`/`data-suffix`, `data-fmt`, `.rv`/`.d1..d6` and the section order intact.
   Recompute bar widths so the largest bar in a group is `100%` and the rest are proportional.
   Keep pill color ↔ status honest (grn/amb/red) and the cover stat cards' `ok`/`warn`/`bad`
   classes aligned to the real status.
4. **Language.** Write all prose in the customer's language (match the language the user is
   working in; default English). Set `<html lang="..">` and, for number formatting, the root
   `data-locale` (e.g. `nl-NL`, `de-DE`) — or per-number `data-fmt`. Keep the design identical.
5. If a section genuinely has no data and no sensible assessment, keep the layout and write
   "No data available" rather than deleting the section.
6. **DAX proof panels.** Give every data section a `<details class="dax-proof"><summary>DAX
   query</summary><pre>…</pre></details>` holding the complete, runnable query that produced
   its numbers. The template already styles these and injects a "Copy DAX" button; they are
   hidden in print/PDF.

---

## Step 5 — Render the PDF, restore real names, open

From the output folder, with `H` = the HTML file and `P` = the PDF file:

```bash
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"   # Chrome path per OS
"$CH" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=8000 \
  --print-to-pdf="$P" "file://$H"
```

The template's `@media print` rules handle the rest (PDF button, demo pill and DAX panels
hidden; gradient text falls back to a solid color; bar fills locked to final width via `--pw`;
`break-inside:avoid` on cards).

**Restore real names (deanonymize).** The report is generated with aliases. To produce the
client-facing version with real names, run the MCP's deanonymizer over the HTML — it uses the
local session mapping and never touches the network:

```bash
python -m server report.html -o report-real.html
```

or open the report in a browser and use the yellow restore bar at the top of the page: drag
`~/.powerbi-mcp/sessions/latest/mapping.json` onto the bar, or click "Load mapping.json" and
pick the file. De-anonymize the PDF source the same way before re-rendering if you need a
real-name PDF.

Then open and verify — don't assert it renders correctly without looking:

- `open "$H"` (browser), `open "$P"` (PDF), `open -R "$P"` (reveal in Finder).
- Screenshot the HTML headless and check it. If the PDF is suspiciously small or 0 pages,
  re-render.

---

## Voice

- Confident and quantified — concrete numbers, no filler. Match the customer's language.
- No em dashes as a stylistic tic, no "Moreover/Furthermore", no promotional inflation, no
  rule-of-three padding. Authentic MSP terms are fine (SLA, tickets, endpoint, MFA,
  DKIM/DMARC, Secure Score, RMM, Copilot, Intune).
- No emoji, no exclamation marks.

---

## Output location

Write to `./QBR-<PERIOD_SHORT>-<Customer>/` containing `QBR-<PERIOD_SHORT>-<Customer>.html`
and `.pdf`. Keep the aliased build alongside the deanonymized `-real` version so the audit
trail is intact.
