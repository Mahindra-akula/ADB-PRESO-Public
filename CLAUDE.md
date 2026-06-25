# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Project

Retail Replenishment Intelligence — Databricks demo. Medallion pipeline (DLT/Lakeflow) + React/FastAPI Databricks App + AI/BI Executive Dashboard + Genie Space. Live signal platform for an 800-store retailer.

**App URL:** https://retail-replenishment-7474655529260099.aws.databricksapps.com  
**App SP UUID (for Unity Catalog grants):** `b768d7ff-8d57-45ca-a0af-669edbe80d32`  
**Executive Dashboard ID:** `01f16c2a8d8c18e6b0b8e2b9ab3e55f6`  
**Genie Space ID:** `01f16817409719d09c80a762fa6a01bf`  
**SQL Warehouse:** `4e7b8de25b26878f` (Serverless Starter)  

## Key Commands

```bash
# Build React frontend (required before every deploy after frontend changes)
cd src/app/frontend && npm run build && cd ../../..

# Deploy all DAB resources
databricks bundle deploy --auto-approve --profile DEFAULT

# Run resources
databricks bundle run data_gen_job --profile DEFAULT
databricks bundle run replenishment_pipeline --profile DEFAULT
databricks bundle run replenishment_app --profile DEFAULT

# Monitor
databricks apps logs retail-replenishment --profile DEFAULT | tail -30
databricks apps get retail-replenishment --profile DEFAULT
```

## Architecture

```
src/
├── data/00_synthetic_data_gen.py     PySpark — catalog/schema/volume + 150K POS rows
├── pipelines/dlt_pipeline.py         DLT — bronze→silver→gold all in retail_data schema
├── notebooks/01_kpi_validation.sql   Demo queries with # DEMO: cues
└── app/                              ← REAL app (NOT app/app.py — that's a dead Dash prototype)
    ├── app.yaml                      uvicorn main:app --host 0.0.0.0 --port 8000
    ├── main.py                       FastAPI + databricks-sdk — 5 endpoints + SPA + /api/order-sku
    ├── requirements.txt              fastapi uvicorn[standard] databricks-sdk
    ├── static/                       React build output (committed, deployed)
    └── frontend/                     React source (excluded via .databricksignore)
        └── src/components/
            ├── Executive.jsx         iframe → Lakeview dashboard embed
            ├── Operations.jsx        Reorder alerts table + Order Now button (per-row email)
            ├── Platform.jsx          Pipeline health stats
            └── Architecture.jsx      Static architecture diagram

resources/
├── data_gen.job.yml
├── replenishment_pipeline.yml        serverless: true, catalog: retail_intelligence, target: retail_data
└── replenishment_app.yml
```

## Workspace

- **Host:** `https://dbc-eaeac0c1-f644.cloud.databricks.com` (DEFAULT profile, AWS, Free Edition)
- **Catalog:** `retail_intelligence` | **Schema:** `retail_data`
- **Volume:** `/Volumes/retail_intelligence/retail_data/raw_pos/`

---

## ABSOLUTE RULES — NEVER VIOLATE THESE

### Language
- SQL first; PySpark only when SQL cannot express the transform
- NEVER use pandas, pd.read_csv, or pd.DataFrame
- NEVER import pandas
- Use `pyspark.sql.functions as F`
- Use `delta.tables.DeltaTable` for MERGE operations

### Platform-First Design
- ALWAYS prefer Databricks native tools: Delta Live Tables over custom orchestration, AI/BI dashboards over external BI, Genie Spaces over custom NLP, Model Serving over custom inference servers
- Only use non-native solutions when a Databricks native option genuinely cannot satisfy the requirement

### Notebook Style
- Flat cell style — NO function wrapping in notebooks
- Direct DataFrame operations at cell level, one table per cell block
- No `def`, no docstrings, no type hints in notebooks

### Databricks Free Edition Platform Rules
- Unity Catalog only — NEVER hive_metastore
- All table refs are three-part: `catalog.schema.table`
- Storage: Unity Catalog Volumes ONLY — path: `/Volumes/{catalog}/{schema}/{volume}/`
- NEVER use `/tmp/` or `/FileStore/` — not available on Free Edition
- Compute: SERVERLESS only — no classic job clusters, no node type pinning
- NO `environment_key`, NO `environments` block, NO `client: "1"` — causes INTERNAL_ERROR

---

## Critical Lessons (Do Not Repeat These Mistakes)

### File confusion — there are TWO app files
- `app/app.py` — dead Dash prototype, **never deployed**, ignore it
- `src/app/main.py` — the real FastAPI backend that IS deployed
- Always verify which file a bundle resource YAML points at before editing

### Free Edition DABs
- Never use `environment_key`, `environments:`, or `client: "1"` → INTERNAL_ERROR
- Serverless is inferred — do not specify node types or spark_version in job clusters

### DLT
- One `target` schema per pipeline — use `retail_data` for all three layers (bronze/silver/gold)
- `channel: PREVIEW`, `serverless: true`, `continuous: false`

### App Backend Auth
- Use **`databricks-sdk`** (`WorkspaceClient()`) — NEVER `databricks-sql-connector`
- `databricks-sql-connector` ignores injected OAuth token, tries to open browser → "no free port" crash
- `WorkspaceClient()` with no args reads `DATABRICKS_HOST` + `DATABRICKS_TOKEN` automatically
- **All SDK `statement_execution` values are strings** — always cast: `int(float(x))` for ROUND/SUM, `int(x)` for COUNT

### Frontend + Deployment
- `frontend/node_modules/` must be in `.databricksignore` BEFORE first deploy — 57MB stalls upload
- Build output `static/` is committed and deployed; source `frontend/` is NOT deployed
- `vite.config.js`: `build: { outDir: '../static' }`
- FastAPI: mount `/assets` first, then catch-all `/{full_path:path}` → `index.html`
- Rebuild React (`npm run build`) before every bundle deploy after frontend changes

### Demo Performance (Critical for live demos)
- **Backend cache**: wrap every read endpoint with a 1-hour `cached(key, fn)` — first hit warms, subsequent hits instant
- **Data lifting**: fetch all API data in App.jsx `useEffect([], [])` once on mount; pass results as props to tab components — eliminates per-tab 2-second warehouse round-trip
- **display:none/block tabs**: render all tab components at all times; show/hide with CSS only — keeps iframe mounted (no reload) and props-received components alive with their data

### Unity Catalog Grants for App SP (first deploy only)
```sql
GRANT USE CATALOG ON CATALOG retail_intelligence TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
```
Use UUID (from `oauth2_app_client_id` in `databricks apps get`), never display name.

### Lakeview AI/BI Dashboard — Widget Spec Rules

**The single most common mistake: missing `spec.data.queryName`**
```python
# WRONG — widget shows title but no data
"spec": {"widgetType": "counter", "encodings": {...}}

# RIGHT — every data widget needs this
"spec": {
    "version": 2,
    "widgetType": "counter",
    "frame": {"title": "My Title", "showTitle": True},
    "encodings": {"value": {"fieldName": "sum(revenue)", "displayName": "Revenue"}},
    "data": {"queryName": "main_query"}   # ← REQUIRED or widget is empty
}
```

**fieldName in encodings must exactly match `name` in query fields:**
```python
# query field definition
{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}

# encoding must reference the same string — "sum(revenue)" not "revenue"
{"fieldName": "sum(revenue)", "displayName": "Revenue"}
```

**Text widgets — pass markdown string directly, not JSON-wrapped:**
```python
# WRONG
"textbox_spec": json.dumps({"text": "## Heading"})  # renders literal JSON

# RIGHT
"textbox_spec": "## Top 5 Priorities\n- Item 1\n- Item 2"
```

**SDK API signatures:**
```python
from databricks.sdk.service.dashboards import Dashboard

# Create — pass a Dashboard object, not keyword args
result = w.lakeview.create(Dashboard(
    display_name="My Dashboard",
    serialized_dashboard=json.dumps(spec),
    warehouse_id="4e7b8de25b26878f",
))

# Publish — dashboard_id and warehouse_id as kwargs, no PublishRequest class
w.lakeview.publish(dashboard_id=result.dashboard_id, warehouse_id="4e7b8de25b26878f")
```

**Other Lakeview rules:**
- `scale.type`: use `"categorical"` not `"ordinal"` for bar chart axes
- `layoutVersion: "GRID_V1"` required in every page object
- 12-column grid — every layout row must sum to `width=12`
- Counter height: 3–4 (never 2)
- `title` goes inside `spec.frame.title`, NOT at the widget wrapper level
- Embedding: iframe loads the **published** version — must click Publish after UI edits

### Lakeview Dashboard Embedding
- The `Executive.jsx` component is just an `<iframe>` pointing at the Lakeview embed URL
- Embed URL format: `https://<host>/embed/dashboardsv3/<dashboard_id>?o=<org_id>`
- After editing the dashboard in the UI, click **Publish** — the iframe auto-refreshes on next page load
- No app redeploy needed for dashboard content changes
