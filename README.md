# Retail Replenishment Intelligence
**Databricks SA Demo — Rebuild in 45–60 Minutes**

A near-real-time POS-driven replenishment signal platform for an 800-store retailer. Medallion pipeline (DLT) → React/FastAPI Databricks App → AI/BI Executive Dashboard → Genie Space.

**Live App:** https://retail-replenishment-7474655529260099.aws.databricksapps.com  
**Executive Dashboard:** https://dbc-eaeac0c1-f644.cloud.databricks.com/dashboardsv3/01f16c2a8d8c18e6b0b8e2b9ab3e55f6/published?o=7474655529260099  
**Genie Space:** https://dbc-eaeac0c1-f644.cloud.databricks.com/genie/rooms/01f16817409719d09c80a762fa6a01bf

---

## The Business Problem

An 800-store retailer is losing revenue to stockouts on high-velocity SKUs. Their demand forecasting runs once a week in Excel — by the time a stockout is flagged, it already happened. The stores are always fixing *last week's* problem.

> **79% stockout rate** across store+SKU combinations. $4.3M weekly revenue at risk.

Their CTO is simultaneously evaluating Databricks, Snowflake, and Microsoft Fabric.

---

## 45-Minute Rebuild Timeline

> **Prerequisites:** Databricks CLI configured (`DEFAULT` profile), Free Edition workspace, Node.js 18+, Python 3.9+

| Time | Step | Command / Action |
|------|------|-----------------|
| 0:00 | Clone & install frontend deps | `cd src/app/frontend && npm install` |
| 0:05 | Build React frontend | `npm run build && cd ../../..` |
| 0:08 | Deploy all DAB resources | `databricks bundle deploy --auto-approve --profile DEFAULT` |
| 0:12 | Generate synthetic data | `databricks bundle run data_gen_job --profile DEFAULT` |
| 0:20 | Run DLT pipeline | `databricks bundle run replenishment_pipeline --profile DEFAULT` |
| 0:30 | Start the app | `databricks bundle run replenishment_app --profile DEFAULT` |
| 0:32 | Grant UC access to app SP | See UC grants section below |
| 0:35 | Create Genie Space | Use Databricks UI or SDK — point at `retail_intelligence.retail_data.*` |
| 0:45 | Create AI/BI dashboard | Use `python create_dashboard.py` pattern (see Lakeview section below) |

**Total: ~45 minutes** (data gen + pipeline run in background while you work on next steps)

---

## Deploy Commands (Copy-Paste Ready)

```bash
# Full deploy from scratch
cd src/app/frontend && npm install && npm run build && cd ../../..
databricks bundle deploy --auto-approve --profile DEFAULT
databricks bundle run data_gen_job --profile DEFAULT
databricks bundle run replenishment_pipeline --profile DEFAULT
databricks bundle run replenishment_app --profile DEFAULT

# After frontend changes — always rebuild before deploy
cd src/app/frontend && npm run build && cd ../../..
databricks bundle deploy --auto-approve --profile DEFAULT
databricks bundle run replenishment_app --profile DEFAULT

# Monitor app logs
databricks apps logs retail-replenishment --profile DEFAULT | tail -30

# Get app SP UUID (needed for UC grants, first deploy only)
databricks apps get retail-replenishment --profile DEFAULT
# → look for oauth2_app_client_id field
```

### Unity Catalog Grants (first deploy only)
```sql
-- Replace UUID with value from oauth2_app_client_id above
GRANT USE CATALOG ON CATALOG retail_intelligence TO `<app-sp-uuid>`;
GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `<app-sp-uuid>`;
GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `<app-sp-uuid>`;
```
Use the UUID, never the display name. Run in a Databricks SQL worksheet.

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
ADB-preso/
├── databricks.yml                        ← DAB root (catalog, workspace host)
├── .databricksignore                     ← CRITICAL: excludes node_modules
├── resources/
│   ├── data_gen.job.yml                  ← serverless job: run data gen script
│   ├── replenishment_pipeline.yml        ← DLT pipeline config
│   └── replenishment_app.yml            ← Databricks App config
└── src/
    ├── data/00_synthetic_data_gen.py     ← PySpark: creates catalog/schema/tables/volumes + data
    ├── pipelines/dlt_pipeline.py         ← DLT: bronze→silver→gold
    ├── notebooks/01_kpi_validation.sql   ← Demo SQL queries
    └── app/
        ├── app.yaml                      ← uvicorn main:app --host 0.0.0.0 --port 8000
        ├── main.py                       ← FastAPI: 5 API endpoints + React SPA serve
        ├── requirements.txt              ← fastapi uvicorn[standard] databricks-sdk
        ├── static/                       ← React build output (committed + deployed)
        └── frontend/                     ← React source (Vite + Recharts, NOT deployed)
            └── src/components/
                ├── Executive.jsx         ← iframe → AI/BI dashboard
                ├── Operations.jsx        ← Reorder alerts table + Order Now button
                ├── Platform.jsx          ← Pipeline health stats
                └── Architecture.jsx      ← Static architecture diagram
```

---

## Critical Gotchas — Lessons Learned the Hard Way

### 1. There are TWO app.py files — edit the right one
- `app/app.py` — old Dash prototype, **NOT deployed**
- `src/app/main.py` — the real FastAPI backend that IS deployed
- `src/app/frontend/` — the real React frontend

### 2. Never use `databricks-sql-connector` in Databricks Apps
```python
# WRONG — ignores injected OAuth token, tries to open browser → crashes
from databricks.sql import connect

# RIGHT — reads DATABRICKS_HOST + DATABRICKS_TOKEN automatically
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
```

### 3. All SDK `statement_execution` values come back as strings
```python
# Always cast:
int(float(row["revenue"]))   # for ROUND/SUM results
int(row["count"])             # for COUNT results
```

### 4. DAB Free Edition — never specify compute
```yaml
# WRONG — causes INTERNAL_ERROR on Free Edition
environments:
  - environment_key: default
    client: "1"

# RIGHT — serverless is inferred, leave it out entirely
```

### 5. DLT — one target schema for all layers
```yaml
# All three layers (bronze/silver/gold) go into one schema
target: retail_data   # NOT bronze/silver/gold as separate schemas
```

### 6. `.databricksignore` must exclude node_modules BEFORE first deploy
```
# .databricksignore
src/app/frontend/node_modules/
src/app/frontend/.vite/
```
If you forget this, the 57MB node_modules stalls the workspace upload permanently.

### 7. Rebuild React before every deploy
```bash
cd src/app/frontend && npm run build && cd ../../..
```
The `static/` folder is what gets deployed. If you skip the build, the app runs old code.

### 8. AI/BI Dashboard widgets need `spec.data.queryName`
Without this field the widget renders the title/frame but shows no data.
```python
# WRONG — widget shows title but no data
"spec": {
    "widgetType": "counter",
    "encodings": {"value": {"fieldName": "my_field"}}
}

# RIGHT
"spec": {
    "version": 2,
    "widgetType": "counter",
    "frame": {"title": "My Title", "showTitle": True},
    "encodings": {"value": {"fieldName": "sum(my_field)", "displayName": "My Title"}},
    "data": {"queryName": "main_query"}   # ← REQUIRED
}
```

### 9. AI/BI Dashboard — field name in query must match fieldName in encodings exactly
```python
# query field name
{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}

# encoding must match — "sum(revenue)" not "revenue"
{"fieldName": "sum(revenue)", "displayName": "Revenue"}
```

### 10. AI/BI Dashboard text widgets — pass markdown directly, not JSON-wrapped
```python
# WRONG — renders {"text": "## Heading"} as literal string
"textbox_spec": json.dumps({"text": "## Heading"})

# RIGHT
"textbox_spec": "## Heading"
```

### 11. Embedding Lakeview dashboards in iframes
Changes made in the Databricks UI editor only appear in the app after you click **Publish** in the dashboard editor. The iframe loads the published version, not the draft.

---

## Lakeview Dashboard — Python Deployment Pattern

Use this pattern to create/update dashboards programmatically (avoids the UI click-through):

```python
import json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

w = WorkspaceClient(profile='DEFAULT')

dashboard_spec = {
    "datasets": [
        {
            "name": "ds_name",
            "displayName": "Display Name",
            "query": "SELECT ... FROM retail_intelligence.retail_data.table"
        }
    ],
    "pages": [{
        "name": "page-1",
        "displayName": "Page 1",
        "pageType": "PAGE_TYPE_CANVAS",
        "layoutVersion": "GRID_V1",   # REQUIRED
        "layout": [
            {
                "widget": {
                    "name": "my-counter",
                    "queries": [{"name": "main_query", "query": {
                        "datasetName": "ds_name",
                        "disaggregated": False,
                        "fields": [{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}]
                    }}],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "frame": {"title": "Revenue", "showTitle": True},
                        "encodings": {"value": {"fieldName": "sum(revenue)", "displayName": "Revenue"}},
                        "data": {"queryName": "main_query"}  # REQUIRED
                    }
                },
                "position": {"x": 0, "y": 0, "width": 4, "height": 3}
            }
        ]
    }]
}

# Create
result = w.lakeview.create(Dashboard(
    display_name="My Dashboard",
    parent_path="/Users/me@example.com",
    serialized_dashboard=json.dumps(dashboard_spec),
    warehouse_id="YOUR_WAREHOUSE_ID",
))

# Publish
w.lakeview.publish(dashboard_id=result.dashboard_id, warehouse_id="YOUR_WAREHOUSE_ID")
print(f"Dashboard ID: {result.dashboard_id}")
```

**Layout rules:**
- 12-column grid — every row must sum to `width=12`
- Counter height: 3–4 (never 2)
- Chart height: 5–6
- Table height: 5–8
- `scale.type`: use `"categorical"` (not `"ordinal"`) for bar chart axes

---

## App — Order Now Email Feature

The Operations tab has an **Order Now** button per row that emails a purchase order. Configure via env vars in `src/app/app.yaml`:

```yaml
env:
  - name: ORDER_EMAIL_TO
    value: "buyer@company.com"
  - name: ORDER_EMAIL_FROM
    value: "replenishment@company.com"
  - name: ORDER_EMAIL_PASSWORD
    value: "your-gmail-app-password"   # Gmail: myaccount.google.com/apppasswords
  - name: SMTP_HOST
    value: "smtp.gmail.com"
  - name: SMTP_PORT
    value: "587"
```

If `ORDER_EMAIL_TO` is not set, the button still shows "✓ Ordered" (demo-safe).

---

## Why Databricks vs Snowflake / Microsoft Fabric

| Capability | Databricks | Snowflake | Microsoft Fabric |
|-----------|-----------|-----------|-----------------|
| Pipeline + BI + App in one platform | ✅ | ❌ Needs dbt + Tableau | ⚠️ Partial |
| Streaming-ready (one line change) | ✅ `read` → `readStream` | ❌ | ❌ |
| Open format (no vendor lock-in) | ✅ Delta in UC Volumes | ❌ Proprietary | ⚠️ OneLake |
| Unity Catalog lineage built-in | ✅ | ❌ Separate tool | ⚠️ Purview |
| Serverless SQL + App hosting | ✅ | ⚠️ SQL only | ⚠️ |
| Native NL interface (Genie) | ✅ | ❌ | ⚠️ Copilot |

---

## Demo Script (60-minute mock customer call)

| Min | What to show | Talking point |
|-----|-------------|---------------|
| 0–5 | Open the app, Executive Overview tab | "This is what the Business Leader sees — live data, no refresh needed" |
| 5–10 | Walk Top 5 Executive Priorities + trendline | "Revenue impact is accelerating faster than stockout count — high-margin items deplete last" |
| 10–15 | Operations tab — reorder alerts table | "The VP of Engineering's morning view — sorted by days of supply, most critical first" |
| 15–18 | Click Order Now on row 1 | "One click triggers a purchase order email. No ERP integration needed for the demo" |
| 18–22 | Platform tab | "CTO view — pipeline row counts, last signal date. Bronze→Silver→Gold, all governed in Unity Catalog" |
| 22–25 | Architecture tab | "End-to-end: DLT pipeline, Unity Catalog, Databricks App, Genie — one platform, zero connectors" |
| 25–35 | Genie Space | "Any ops team member can ask 'which stores in the Northeast need reordering today?' in plain English" |
| 35–45 | Handle Q&A — see likely questions below | |

**Likely panel questions:**
- *"How does this scale to 800 stores?"* → Change 100→800 in data gen, zero architecture changes. DLT is serverless, autoscales.
- *"What about streaming?"* → `spark.read.parquet` → `spark.readStream.format("cloudFiles")` — literally one line.
- *"How do you handle data quality?"* → Show DLT expectations in `dlt_pipeline.py` — `@dlt.expect("valid_qty", "qty_sold >= 0")`.
- *"What's the latency?"* → With streaming, signals fire within minutes of a POS transaction. Demo is batch (daily) for simplicity.
- *"Can non-technical users query this?"* → Switch to Genie tab and ask a question live.
