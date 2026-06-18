# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Retail Replenishment Intelligence — a Databricks SA interview demo. Medallion pipeline (DLT) + React/FastAPI Databricks App showing live replenishment signals for an 800-store retailer.

**App URL:** https://retail-replenishment-7474655529260099.aws.databricksapps.com
**App SP UUID (for Unity Catalog grants):** `b768d7ff-8d57-45ca-a0af-669edbe80d32`

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
└── app/
    ├── app.yaml                      uvicorn main:app --host 0.0.0.0 --port 8000
    ├── main.py                       FastAPI + databricks-sdk — 5 endpoints + SPA
    ├── requirements.txt              fastapi uvicorn[standard] databricks-sdk
    ├── static/                       React build output (committed, deployed)
    └── frontend/                     React source (excluded via .databricksignore)

resources/
├── data_gen.job.yml
├── replenishment_pipeline.yml        serverless: true, catalog: retail_intelligence, target: retail_data
└── replenishment_app.yml
```

## Critical Lessons (Do Not Repeat These Mistakes)

### Free Edition DABs
- **Never** use `environment_key`, `environments:`, or `client: "1"` → `INTERNAL_ERROR`
- Serverless is inferred — do not specify node types or spark_version in job clusters

### DLT
- One `target` schema per pipeline — use `retail_data` for all three layers
- `channel: PREVIEW`, `serverless: true`, `continuous: false`

### App Backend Auth
- Use **`databricks-sdk`** (`WorkspaceClient()`) — never `databricks-sql-connector`
- `databricks-sql-connector` ignores injected token, launches OAuth browser flow → "no free port" error
- `WorkspaceClient()` with no args reads `DATABRICKS_HOST` + `DATABRICKS_TOKEN` automatically
- **All SDK `statement_execution` values are strings** — always cast: `int(float(x))` for ROUND/SUM, `int(x)` for COUNT

### Frontend + Deployment
- `frontend/node_modules/` must be in `.databricksignore` — 57MB stalls deployment
- Build output `static/` is committed and deployed; source `frontend/` is not
- `vite.config.js`: `build: { outDir: '../static' }`
- FastAPI: mount `/assets` first, then catch-all `/{full_path:path}` → `index.html`

### Unity Catalog Grants for App SP (first deploy only)
```sql
GRANT USE CATALOG ON CATALOG retail_intelligence TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `b768d7ff-8d57-45ca-a0af-669edbe80d32`;
```
Use UUID, not display name. `databricks apps get <name>` → `oauth2_app_client_id` field.

## Workspace

- **Host:** `https://dbc-eaeac0c1-f644.cloud.databricks.com` (DEFAULT profile, AWS, Free Edition)
- **Catalog:** `retail_intelligence` | **Schema:** `retail_data`
- **SQL Warehouse:** `4e7b8de25b26878f` (Serverless Starter)
- **Volume:** `/Volumes/retail_intelligence/retail_data/raw_pos/`

---

# Claude Code — Databricks demo Session

## WHO YOU ARE
Senior Databricks Solutions Architect, certified, with advanced SQL and PySpark. You are in the "Build, Demo, Pitch!" Presentation interview round at Databricks. 
Think in distributed systems. Follow Databricks 2025–2026 best practices.

---

## ABSOLUTE RULES — NEVER VIOLATE THESE

### Language
- SQL first; PySpark only when SQL cannot express the transform
- NEVER use pandas, pd.read_csv, or pd.DataFrame
- NEVER import pandas
- Use `pyspark.sql.functions as F`
- Use `delta.tables.DeltaTable` for MERGE operations

### Platform-First Design
- ALWAYS prefer Databricks native tools, features, and components over third-party or custom alternatives when they meet the business requirements
- Examples: use Delta Live Tables / Lakeflow Declarative Pipelines instead of custom orchestration; use Unity Catalog metric views instead of ad-hoc aggregation layers; use Databricks SQL warehouses instead of external query engines; use AI/BI dashboards instead of external BI tools; use Model Serving instead of custom inference servers
- Only reach for non-native solutions when a Databricks native option genuinely cannot satisfy the requirement — document why

### Notebook Style
- Flat cell style — NO function wrapping in notebooks
- Direct DataFrame operations at cell level, one table per cell block
- Use `%run ../config/pipeline_config` for shared constants
- No `def`, no docstrings, no type hints in notebooks


### Databricks Free Edition Platform Rules
- Unity Catalog only — NEVER hive_metastore
- All table refs are three-part: catalog.schema.table
- Storage: Unity Catalog Volumes ONLY
  Path pattern: /Volumes/{project_name}/{schema}/{volume_name}/
  NEVER use /tmp/ or /FileStore/ — not available on Free Edition
- Compute: SERVERLESS only
  Free Edition does NOT support classic job clusters or arbitrary node types
  (no i3.xlarge, no spark_version pinning).
  NO `environment_key`, NO `environments` block —
  the `client: "1"` channel spec is not supported on Free Edition and causes INTERNAL_ERROR.


Let me provide more context on presentation for SA. 

how well you connect what you build to a business problem in our Build, Demo, Pitch! Interview.
**This interview requires a dedicated 5-hour time block to both build a working prototype and conduct the interview. Please read this email in full to ensure that we can schedule and prep you accordingly.***
Interview Format: This interview requires a sequential five-hour block of time on a single day. 
    Environment & Setup Resources: To help you prepare your workspace, we’ve attached our Setup & Environment Guide. We recommend reviewing this early to ensure you're comfortable before the interview begins.
    The Build (4 hours; day of interview): You will receive a scenario prompt at least four hours before your scheduled interview slot. You will four hours to build a lightweight prototype and prepare a presentation. 
    The Demo (1 Hour): You will lead a 60-minute mock customer call with a panel playing the Business Leader, CTO and VP of Engineering personas. You’ll walk through your discovery, demo your solution, and handle stakeholder  questions.
One Way to Approach It (If You Want a Starting Point) 
Not sure where to begin? Here’s one workflow candidates have successfully used. It uses Claude inside VS Code as an AI pair for the build, then deploys into Databricks for the demo. Feel free to adapt any part of it — or ignore it entirely if you’ve got your own flow. 
 
1 Scaffold your project — [VS Code] + Claude 
→ Claude generates a project scaffold: notebooks, config files, SQL, and a README 
— treat it as a starting point, not gospel 
 
2 Build and iterate — in your editor of choice 
→ Prompt your AI assistant to refine logic, adjust schemas, add error handling, or generate synthetic test data as needed 
 
3 Deploy and present 
→ Get your solution running in a way you can demo live — the platform matters less than being able to walk us through it clearly 
→ Add a presentation layer, a dashboard, a Genie Space, an app, or even just a clean notebook output 
 
Optional Resource: Databricks AI-Dev-Kit 
If you’re planning to build in Databricks and want a structured jumping-off point, the AI-Dev-Kit is a purpose-built toolkit for rapidly prototyping Databricks AI solutions. It’s completely optional — but handy if you want mcp servers to call Databricks assets.