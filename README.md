# Retail Replenishment Intelligence

A near-real-time POS-driven replenishment signal platform for an 800-store retailer. Built end-to-end on Databricks using a medallion architecture — from raw POS transactions to executive dashboards and natural language querying.

**Stack:** Lakeflow Declarative Pipelines (DLT) · Unity Catalog · FastAPI · React 18 · Databricks Apps · AI/BI Lakeview Dashboard · Genie Space

---

## The Problem

An 800-store retailer is losing revenue to stockouts on high-velocity SKUs. Demand forecasting runs once a week — by the time a stockout is flagged, it already happened.

> **79% stockout rate** across store+SKU combinations. $4.3M weekly revenue at risk.

This project replaces the weekly batch Excel process with a near-real-time signal platform that surfaces REORDER NOW alerts to operations teams each morning.

---

## Architecture

```
POS Transactions (100 stores × 50 SKUs × 30 days = 150K rows)
        │
        ▼  Lakeflow Declarative Pipelines (DLT, serverless)
  BRONZE → SILVER → GOLD   (all in retail_intelligence.retail_data)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│              Databricks App                         │
│  React 18 + Vite + FastAPI + databricks-sdk         │
│                                                     │
│  Executive Overview  │  Operations Command Center   │
│  (AI/BI Dashboard)   │  (Reorder alerts + Order Now)│
│                      │                             │
│  Platform & Governance  │  Solution Architecture   │
└─────────────────────────────────────────────────────┘
        │
        ▼
  AI/BI Dashboard (Lakeview) — embedded in Executive tab
  Genie Space — natural language queries on gold table
```

### Unity Catalog Layout
```
retail_intelligence (catalog)
└── retail_data (schema)
    ├── stores                   — 100 stores, 5 regions, state
    ├── skus                     — 50 SKUs, 8 categories, avg_unit_price
    ├── pos_transactions_raw     — Bronze: 150K raw POS rows
    ├── pos_store_sku_signals    — Silver: 7 & 14-day rolling demand per store+SKU
    └── replenishment_signals    — Gold: REORDER NOW / WATCH / OK per store+SKU
```

---

## File Structure

```
├── databricks.yml                        ← DAB root (catalog, workspace host)
├── .databricksignore                     ← excludes node_modules from deploy
├── resources/
│   ├── data_gen.job.yml                  ← serverless job: run data gen script
│   ├── replenishment_pipeline.yml        ← DLT pipeline config
│   └── replenishment_app.yml             ← Databricks App config
└── src/
    ├── data/00_synthetic_data_gen.py     ← PySpark: creates catalog/schema/tables/volumes + data
    ├── pipelines/dlt_pipeline.py         ← DLT: bronze→silver→gold
    ├── notebooks/01_kpi_validation.sql   ← Validation SQL queries
    └── app/
        ├── app.yaml                      ← uvicorn main:app --host 0.0.0.0 --port 8000
        ├── main.py                       ← FastAPI: 5 API endpoints + React SPA serve
        ├── requirements.txt              ← fastapi uvicorn[standard] databricks-sdk
        ├── static/                       ← React build output (committed + deployed)
        └── frontend/                     ← React source (Vite + Recharts, NOT deployed)
            └── src/components/
                ├── Executive.jsx         ← iframe → AI/BI Lakeview dashboard embed
                ├── Operations.jsx        ← Reorder alerts table + Order Now button
                ├── Platform.jsx          ← Pipeline health stats
                └── Architecture.jsx      ← Static architecture diagram
```

---

## Quickstart

**Prerequisites:** Databricks CLI configured, Free Edition workspace, Node.js 18+, Python 3.9+

```bash
# 1. Build React frontend
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy all DAB resources
databricks bundle deploy --auto-approve

# 3. Generate synthetic data
databricks bundle run data_gen_job

# 4. Run DLT pipeline (bronze → silver → gold)
databricks bundle run replenishment_pipeline

# 5. Start the app
databricks bundle run replenishment_app

# Monitor logs
databricks apps logs retail-replenishment | tail -30
```

### Unity Catalog Grants (first deploy only)
After deploy, grant the app's service principal access to the catalog:
```sql
-- Get the SP UUID from: databricks apps get retail-replenishment → oauth2_app_client_id
GRANT USE CATALOG ON CATALOG retail_intelligence TO `<app-sp-uuid>`;
GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `<app-sp-uuid>`;
GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `<app-sp-uuid>`;
```

---

## Key Engineering Decisions

### 1. databricks-sdk, not databricks-sql-connector
```python
# WRONG — ignores injected OAuth token in Databricks Apps, tries to open browser → crashes
from databricks.sql import connect

# RIGHT — reads DATABRICKS_HOST + DATABRICKS_TOKEN automatically from the app environment
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
```

### 2. All SDK `statement_execution` values return as strings
```python
# Always cast before arithmetic or returning from API:
int(float(row["revenue"]))   # for ROUND/SUM results
int(row["count"])             # for COUNT results
```

### 3. Free Edition DABs — never specify compute explicitly
```yaml
# WRONG — causes INTERNAL_ERROR on Free Edition
environments:
  - environment_key: default
    client: "1"

# RIGHT — serverless is inferred, omit entirely
```

### 4. DLT — single target schema for all layers
```yaml
# All three layers (bronze/silver/gold) land in one schema
target: retail_data   # not bronze/silver/gold as separate schemas
```

### 5. `.databricksignore` must exclude node_modules before first deploy
```
src/app/frontend/node_modules/
src/app/frontend/.vite/
```
The 57MB node_modules directory stalls the workspace upload permanently if included.

### 6. Rebuild React before every deploy
```bash
cd src/app/frontend && npm run build && cd ../../..
```
The `static/` folder is what gets deployed — skipping the build ships stale code.

---

## Performance Design

Two techniques keep the app instant during live use:

**Backend: 1-hour in-memory cache**
Every read endpoint is wrapped with a `cached(key, fn)` helper. First API call hits the SQL warehouse (~2–5s); all subsequent calls within 1 hour return from memory. No warehouse cold-start visible to users.

**Frontend: data lifting + CSS-only tab switching**
All API endpoints are fetched once in `App.jsx` on mount and passed as props — no component makes its own `fetch()` call. Tabs use `display: none/block` rather than unmounting, which keeps the Executive iframe alive (no reload on tab switch).

```jsx
// App.jsx — single useEffect, all data loaded once on mount
useEffect(() => {
  fetch('/api/top-alerts').then(r => r.json()).then(setAlerts)
  fetch('/api/regional').then(r => r.json()).then(setRegional)
}, [])

// Tab switching — CSS only, all components stay mounted
<div style={{ display: active === 'operations' ? 'block' : 'none' }}>
  <Operations alerts={alerts} regional={regional} />
</div>
```

---

## Order Now Feature

The Operations tab includes a per-row **Order Now** button that emails a purchase order. Configure via environment variables in `src/app/app.yaml`:

```yaml
env:
  - name: ORDER_EMAIL_TO
    value: "buyer@company.com"
  - name: ORDER_EMAIL_FROM
    value: "replenishment@company.com"
  - name: ORDER_EMAIL_PASSWORD
    value: "your-gmail-app-password"
  - name: SMTP_HOST
    value: "smtp.gmail.com"
  - name: SMTP_PORT
    value: "587"
```

If `ORDER_EMAIL_TO` is not set, the button still renders and shows a confirmation (email silently skipped).

---

## AI/BI Dashboard — Lakeview Python Deployment

Dashboards can be created/updated programmatically:

```python
import json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

w = WorkspaceClient()

dashboard_spec = {
    "datasets": [{"name": "ds_name", "displayName": "Display Name",
                  "query": "SELECT ... FROM retail_intelligence.retail_data.replenishment_signals"}],
    "pages": [{
        "name": "page-1",
        "displayName": "Overview",
        "pageType": "PAGE_TYPE_CANVAS",
        "layoutVersion": "GRID_V1",   # required
        "layout": [{
            "widget": {
                "name": "revenue-counter",
                "queries": [{"name": "main_query", "query": {
                    "datasetName": "ds_name",
                    "disaggregated": False,
                    "fields": [{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}]
                }}],
                "spec": {
                    "version": 2,
                    "widgetType": "counter",
                    "frame": {"title": "Revenue at Risk", "showTitle": True},
                    "encodings": {"value": {"fieldName": "sum(revenue)", "displayName": "Revenue"}},
                    "data": {"queryName": "main_query"}   # required — widget is blank without this
                }
            },
            "position": {"x": 0, "y": 0, "width": 4, "height": 3}
        }]
    }]
}

result = w.lakeview.create(Dashboard(
    display_name="Retail Replenishment Overview",
    serialized_dashboard=json.dumps(dashboard_spec),
    warehouse_id="YOUR_WAREHOUSE_ID",
))
w.lakeview.publish(dashboard_id=result.dashboard_id, warehouse_id="YOUR_WAREHOUSE_ID")
```

**Layout rules:** 12-column grid, every row sums to `width=12`. Counter height 3–4. Chart height 5–6.

**Common gotcha:** `spec.data.queryName` is required on every data widget — omitting it renders a blank widget with just the title frame.
