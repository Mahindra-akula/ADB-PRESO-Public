# Skill: Databricks App — React + FastAPI + Databricks SDK

A reusable pattern for building multi-tab Databricks Apps with live SQL data, no iframes, and automatic service principal auth.

**When to use this over Dash + iframe:**
- Dashboards use X-Frame-Options headers that block iframe embedding
- You need custom charts (Recharts, D3) not available in AI/BI dashboards
- You want a single self-contained deployment with no external dashboard URLs to manage

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React 18 + Vite + Recharts | Fast build, rich charts, small bundle |
| Backend | FastAPI + uvicorn | Async, lightweight, serves React SPA |
| Auth | `databricks-sdk` `WorkspaceClient()` | Auto-reads injected token; sql-connector fails |
| Data | `statement_execution` API | REST-based, works with SP M2M auth |
| Deployment | Databricks Asset Bundles (DABs) | Single command, handles App lifecycle |

---

## File Structure

```
project/
├── databricks.yml
├── .databricksignore          ← CRITICAL: exclude node_modules
├── resources/
│   └── my_app.yml
└── src/
    └── app/
        ├── app.yaml           ← uvicorn command + env vars
        ├── main.py            ← FastAPI backend
        ├── requirements.txt   ← fastapi uvicorn[standard] databricks-sdk
        ├── static/            ← React build output (committed)
        └── frontend/          ← React source (excluded from deploy)
            ├── package.json
            ├── vite.config.js
            └── src/
                ├── App.jsx
                └── components/
```

---

## Checklist: New App

### 1 · `.databricksignore` (copy this exactly)
```
src/app/frontend/node_modules/
src/app/frontend/src/
src/app/frontend/public/
src/app/frontend/package.json
src/app/frontend/package-lock.json
src/app/frontend/vite.config.js
src/app/frontend/index.html
```
**Why:** `node_modules` is 57MB+. Without this, every `bundle deploy` uploads the full npm tree and stalls the "Preparing source code" step — or causes mid-deploy `RESOURCE_DOES_NOT_EXIST` failures.

### 2 · `resources/my_app.yml`
```yaml
resources:
  apps:
    my_app:
      name: "my-app-name"          # Must be unique in workspace
      description: "My App"
      source_code_path: ../src/app
```

### 3 · `src/app/app.yaml`
```yaml
command:
  - uvicorn
  - main:app
  - --host
  - "0.0.0.0"
  - --port
  - "8000"
env:
  - name: WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: CATALOG
    value: "your_catalog"
  - name: SCHEMA
    value: "your_schema"
```

### 4 · `src/app/requirements.txt`
```
fastapi
uvicorn[standard]
databricks-sdk
```
**Never use** `databricks-sql-connector` in Apps — it tries OAuth browser flow and fails.

### 5 · `src/app/main.py` (template)
```python
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI()

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "fallback-id")
CATALOG  = os.environ.get("CATALOG", "my_catalog")
SCHEMA   = os.environ.get("SCHEMA", "my_schema")

_client = None
def get_client():
    global _client
    if _client is None:
        _client = WorkspaceClient()   # Auto-reads DATABRICKS_HOST + DATABRICKS_TOKEN
    return _client


def query(sql_text: str) -> list[dict]:
    """
    Execute SQL via statement execution API.
    IMPORTANT: All returned values are STRINGS regardless of SQL type.
    Cast explicitly: int(float(x)) for ROUND/SUM, int(x) for COUNT.
    """
    result = get_client().statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_text,
        wait_timeout="50s",
    )
    if result.status.state != StatementState.SUCCEEDED:
        err = result.status.error
        raise RuntimeError(f"Query failed: {err.message if err else result.status.state}")
    cols = [col.name for col in result.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (result.result.data_array or [])]


# ── Your API routes here ───────────────────────────────────────────────────────

@app.get("/api/example")
def example():
    rows = query(f"SELECT id, COUNT(*) AS cnt FROM {CATALOG}.{SCHEMA}.my_table GROUP BY id")
    return [{"id": r["id"], "count": int(r["cnt"])} for r in rows]


# ── Serve React SPA — order matters ───────────────────────────────────────────
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    return FileResponse("static/index.html")
```

### 6 · `src/app/frontend/vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',   // Output lands in src/app/static/ — deployed to workspace
    emptyOutDir: true,
  },
  server: {
    proxy: { '/api': 'http://localhost:8000' }  // Dev: proxy API to local FastAPI
  }
})
```

### 7 · `src/app/frontend/package.json` (minimal)
```json
{
  "name": "app-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.13.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^5.4.19"
  }
}
```

---

## Type Conversion Reference

The `statement_execution` API returns **all values as strings** in `data_array`. Always cast:

```python
# SQL COUNT(*) → '100' → int directly works
int(row["count"])

# SQL ROUND(SUM(...), 0) → '4350213.0' → int() fails! Use float() first
int(float(row["revenue"]))

# SQL ROUND(val, 1) → '79.1' → float
float(row["pct"])

# SQL MAX(date) → '2026-06-18' → keep as string or parse
str(row["last_updated"])
```

---

## Unity Catalog Grants for App Service Principal

The App creates its own service principal. Grant it access **after** the first `bundle run`:

```bash
# Get the SP UUID
databricks apps get my-app-name --profile DEFAULT | python -c "import sys,json; print(json.load(sys.stdin)['oauth2_app_client_id'])"
```

```python
# Grant access (run once — UUID is stable across redeploys)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient(profile='DEFAULT')
sp_uuid = "<paste-uuid>"

for stmt in [
    f"GRANT USE CATALOG ON CATALOG my_catalog TO `{sp_uuid}`",
    f"GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `{sp_uuid}`",
    f"GRANT SELECT ON SCHEMA my_catalog.my_schema TO `{sp_uuid}`",
]:
    r = w.statement_execution.execute_statement(
        warehouse_id='your-warehouse-id', statement=stmt, wait_timeout='30s'
    )
    print(r.status.state.value, stmt[:60])
```

> Use the UUID (e.g. `b768d7ff-8d57-45ca-a0af-669edbe80d32`), not the display name (e.g. `app-568qat my-app`) — the display name is not a valid Unity Catalog principal identifier.

---

## Deployment Sequence

```bash
# 1. Build frontend (after any React changes)
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy resources (fast — node_modules excluded by .databricksignore)
databricks bundle deploy --auto-approve --profile DEFAULT

# 3. Start the app
databricks bundle run my_app --profile DEFAULT

# 4. First time only: grant SP permissions
#    (get UUID, run grants, then restart)
databricks bundle run my_app --profile DEFAULT

# 5. Check logs
databricks apps logs my-app-name --profile DEFAULT | tail -30
```

**Deployment is fast (~3s) once `node_modules` is excluded.** The key log lines to look for:
```
[BUILD] Starting app with command: [uvicorn main:app --host 0.0.0.0 --port 8000]
[APP]   Uvicorn running on http://0.0.0.0:8000
[BUILD] Deployment successful
```

---

## React Tab Pattern (App.jsx)

```jsx
import { useState } from 'react'
import Executive from './components/Executive'
import Operations from './components/Operations'
// ... other tabs

const TABS = [
  { key: 'executive',   label: 'Executive Overview',    Component: Executive },
  { key: 'operations',  label: 'Ops Command Center',    Component: Operations },
]

export default function App() {
  const [active, setActive] = useState('executive')
  const { Component } = TABS.find(t => t.key === active)

  return (
    <div style={{ fontFamily: 'Inter, sans-serif', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '16px 32px', borderBottom: '1px solid #eee', background: '#fff' }}>
        <div style={{ fontWeight: 700, fontSize: 18, color: '#FF3621' }}>App Title</div>
      </div>

      {/* Nav */}
      <div style={{ display: 'flex', gap: 8, padding: '12px 32px', background: '#fafafa', borderBottom: '1px solid #eee' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setActive(t.key)}
            style={{
              padding: '7px 18px', borderRadius: 6, cursor: 'pointer', fontWeight: 600,
              border: '1px solid #FF3621',
              background: active === t.key ? '#FF3621' : '#fff',
              color:      active === t.key ? '#fff'    : '#FF3621',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <Component />
      </div>
    </div>
  )
}
```

## Data Fetching Pattern (per component)

```jsx
import { useEffect, useState } from 'react'

export default function MyTab() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    fetch('/api/my-endpoint').then(r => r.json()).then(setData).catch(setErr)
  }, [])

  if (err)  return <div style={{ padding: 40, color: '#e74c3c' }}>Error: {err.message}</div>
  if (!data) return <div style={{ padding: 40, color: '#888' }}>Loading...</div>

  return <div>{/* render data */}</div>
}
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Deploy stuck "Preparing source code" | `node_modules` in workspace from earlier deploy without `.databricksignore` | `databricks workspace delete --recursive .../frontend` then redeploy |
| `ValueError: invalid literal for int()` | SQL `ROUND()`/`SUM()` returns float-string like `'4350213.0'` | Use `int(float(x))` |
| 500 on all API routes — "no free port" | Using `databricks-sql-connector` which tries OAuth browser auth | Replace with `databricks-sdk` |
| 500 — Permission denied | App SP lacks Unity Catalog grants | Run GRANT statements with SP UUID |
| App shows old version after redeploy | New files deployed but app not restarted | `databricks bundle run <app_resource_key>` |
| `curl` returns 401 `{}` | Databricks Apps requires browser OAuth for all routes | Expected — test in browser only |
| SP GRANT fails "principal not found" | Used display name instead of UUID | Use `oauth2_app_client_id` from `databricks apps get` |
