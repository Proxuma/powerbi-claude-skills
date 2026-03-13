# Power BI Business Question

Answer the following business question using Power BI data:

**Question:** $ARGUMENTS

**If no question is specified, ask the user what they want to know.**

## Instructions

Follow this **memory-safe strategy** to answer the question. NEVER use `get_schema` as it can return >10MB and crash the session.

### Step 0: Discover workspace and dataset

If you don't already know the user's workspace and dataset IDs, find them:

```
mcp__powerbi__list_workspaces()
```

Then for the relevant workspace:

```
mcp__powerbi__list_datasets(workspace_id="<WORKSPACE_ID>")
```

If there are multiple workspaces or datasets, ask the user which one to use. Remember the IDs for subsequent queries.

### Step 1: Identify keywords

Extract 2-3 key business terms from the question (e.g., "revenue", "sales", "efficiency", "margin").

### Step 2: Search for relevant measures

For each keyword, use `search_schema` to find relevant measures and their definitions:

```
mcp__powerbi__search_schema(
    workspace_id="<WORKSPACE_ID>",
    dataset_id="<DATASET_ID>",
    search_term="<keyword>"
)
```

This returns only matching definitions with context (not the full schema).

### Step 3: Build and execute DAX query

Based on the measures found, construct a targeted DAX query:

```
mcp__powerbi__execute_dax(
    dataset_id="<DATASET_ID>",
    dax_query="EVALUATE SUMMARIZECOLUMNS(...)"
)
```

Common DAX patterns:
- **Top N:** `EVALUATE TOPN(10, 'Table', [Measure], DESC)`
- **Summary:** `EVALUATE SUMMARIZECOLUMNS('Dim'[Column], "Total", [Measure])`
- **Filter:** `EVALUATE CALCULATETABLE('Table', 'Dim'[Column] = "Value")`
- **Time intelligence:** Use `DATESYTD`, `SAMEPERIODLASTYEAR`, etc.

### Step 4: Answer the question

Provide a clear, concise answer based on the DAX query results. Include:
- The actual numbers/data
- Brief interpretation
- Any relevant context from the measure definitions

## Memory Safety Rules

1. **NEVER** use `get_schema` - it returns the full model (>10MB)
2. **ALWAYS** use `search_schema` with specific terms
3. **LIMIT** DAX results with `TOPN()` or filters
4. If `list_measures` is needed for overview, use it once and cache mentally
5. Keep searches focused - max 3 search terms per question
