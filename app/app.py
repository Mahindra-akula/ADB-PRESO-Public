import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State, ALL

from databricks.sdk import WorkspaceClient

# ── Config ─────────────────────────────────────────────────────────────────────
WAREHOUSE_ID = "4e7b8de25b26878f"

# ── Dashboard URLs — paste published AI/BI dashboard URLs here ─────────────────
DASHBOARDS = {
    "executive": {
        "label":    "Executive Overview",
        "url":      "PASTE_EXECUTIVE_DASHBOARD_URL_HERE",
        "audience": "Business Leader — stockout rate, revenue at risk, 30-day trend",
    },
    "platform": {
        "label":    "Platform & Governance",
        "url":      "PASTE_PLATFORM_DASHBOARD_URL_HERE",
        "audience": "CTO — DLT pipeline lineage, Unity Catalog governance, pipeline health",
    },
}


# ── Data helpers ───────────────────────────────────────────────────────────────
def fetch_reorder_alerts():
    w = WorkspaceClient()
    sql = """
        SELECT store_id, sku_id, inventory_on_hand,
               days_of_supply, avg_daily_demand_7d, replenishment_status
        FROM retail_intelligence.retail_data.replenishment_signals
        WHERE replenishment_status = 'REORDER NOW'
        ORDER BY days_of_supply ASC
        LIMIT 50
    """
    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        wait_timeout="30s",
    )
    cols = [c.name for c in resp.manifest.schema.columns]
    rows = resp.result.data_array or []
    return [dict(zip(cols, r)) for r in rows]


def send_order_email(row):
    to_addr = os.environ.get("ORDER_EMAIL_TO", "")
    if not to_addr:
        return

    from_addr = os.environ.get("ORDER_EMAIL_FROM", "replenishment@retail-demo.com")
    password  = os.environ.get("ORDER_EMAIL_PASSWORD", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg["Subject"] = f"URGENT: Purchase Order — SKU {row['sku_id']} · Store {row['store_id']}"

    body = (
        f"AUTOMATED REPLENISHMENT ORDER\n"
        f"{'─'*40}\n"
        f"Store:             {row['store_id']}\n"
        f"SKU:               {row['sku_id']}\n"
        f"Current Stock:     {row['inventory_on_hand']} units\n"
        f"Days of Supply:    {row['days_of_supply']} days\n"
        f"Avg Daily Demand:  {row['avg_daily_demand_7d']} units/day\n\n"
        f"Status: REORDER NOW — stock critically low.\n\n"
        f"This order was triggered from the Retail Replenishment Intelligence platform."
    )
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as srv:
            srv.starttls()
            if password:
                srv.login(from_addr, password)
            srv.sendmail(from_addr, to_addr, msg.as_string())
    except Exception:
        pass


# ── Operations layout ──────────────────────────────────────────────────────────
STATUS_COLOR = {"REORDER NOW": "#c0392b", "WATCH": "#d35400", "OK": "#27ae60"}

def operations_layout(rows):
    header = html.Div([
        html.H3("Top Reorder Alerts — Most Urgent First",
                style={"margin": "0 0 4px 0", "color": "#1a1a1a", "fontSize": "18px"}),
        html.P(f"{len(rows)} SKU/store combinations require immediate replenishment",
               style={"margin": 0, "color": "#888", "fontSize": "12px"}),
    ], style={"marginBottom": "20px"})

    th_style = {
        "padding": "10px 14px", "textAlign": "left",
        "fontSize": "12px", "fontWeight": "700",
        "color": "#555", "borderBottom": "2px solid #e0e0e0",
        "whiteSpace": "nowrap",
    }
    td_style = {
        "padding": "10px 14px", "fontSize": "13px",
        "borderBottom": "1px solid #f0f0f0", "whiteSpace": "nowrap",
    }

    table_header = html.Tr([
        html.Th("Store",              style=th_style),
        html.Th("SKU",                style=th_style),
        html.Th("On Hand (units)",    style=th_style),
        html.Th("Days of Supply",     style=th_style),
        html.Th("Avg Daily Demand",   style=th_style),
        html.Th("",                   style=th_style),  # button column
    ])

    table_rows = []
    for row in rows:
        dos = float(row["days_of_supply"]) if row["days_of_supply"] else 0
        dos_color = "#c0392b" if dos < 2 else "#d35400" if dos < 4 else "#1a1a1a"
        btn_key = f"{row['store_id']}|{row['sku_id']}"
        table_rows.append(html.Tr([
            html.Td(row["store_id"],                        style=td_style),
            html.Td(row["sku_id"],                          style=td_style),
            html.Td(int(float(row["inventory_on_hand"])),   style=td_style),
            html.Td(
                f"{dos:.1f}d",
                style={**td_style, "color": dos_color, "fontWeight": "700"},
            ),
            html.Td(
                f"{float(row['avg_daily_demand_7d']):.1f} units/day",
                style=td_style,
            ),
            html.Td(
                html.Button(
                    "Order Now",
                    id={"type": "order-btn", "index": btn_key},
                    n_clicks=0,
                    style={
                        "background": "#FF3621", "color": "#fff",
                        "border": "none", "borderRadius": "4px",
                        "padding": "6px 14px", "cursor": "pointer",
                        "fontSize": "12px", "fontWeight": "700",
                    },
                ),
                style=td_style,
            ),
        ]))

    table = html.Table(
        [html.Thead(table_header), html.Tbody(table_rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )

    return html.Div([
        header,
        html.Div(id="order-toast", style={"marginBottom": "16px"}),
        html.Div(table, style={"overflowX": "auto"}),
    ], style={"padding": "32px 40px", "overflowY": "auto",
              "height": "100%", "boxSizing": "border-box"})


# ── Architecture tab ───────────────────────────────────────────────────────────
def architecture_layout():
    def box(label, color, detail):
        return html.Div([
            html.Div(label, style={"fontWeight": "700", "fontSize": "13px", "color": "#fff"}),
            html.Div(detail, style={"fontSize": "11px", "color": "rgba(255,255,255,0.75)",
                                    "marginTop": "6px", "lineHeight": "1.5"}),
        ], style={
            "background": color, "borderRadius": "8px", "padding": "16px 18px",
            "minWidth": "155px", "textAlign": "center", "flexShrink": "0",
        })

    def arrow():
        return html.Div("→", style={"fontSize": "22px", "color": "#bbb",
                                     "alignSelf": "center", "padding": "0 10px", "flexShrink": "0"})

    def down_arrow():
        return html.Div("↓", style={"textAlign": "center", "fontSize": "22px",
                                     "color": "#bbb", "margin": "14px 0"})

    return html.Div([
        html.H2("Solution Architecture",
                style={"color": "#1a1a1a", "marginBottom": "4px", "fontSize": "22px"}),
        html.P("Retail Replenishment Intelligence · Databricks Free Edition · Serverless",
               style={"color": "#777", "marginBottom": "36px", "fontSize": "13px"}),

        html.Div([
            box("POS Transactions",  "#3d3d3d",
                "100 stores · 50 SKUs\n150K rows / 30 days\n(scales to 800 stores)"),
            arrow(),
            box("Bronze",            "#c0392b",
                "Raw ingestion\nDelta Live Tables\nAuto Loader ready"),
            arrow(),
            box("Silver",            "#d35400",
                "Deduped + typed\n7 & 14-day rolling\ndemand signals"),
            arrow(),
            box("Gold",              "#27ae60",
                "Replenishment signals\nDays of supply\nREORDER NOW / WATCH / OK"),
        ], style={"display": "flex", "alignItems": "stretch",
                  "justifyContent": "center", "flexWrap": "wrap", "gap": "4px"}),

        down_arrow(),

        html.Div([
            box("Executive Dashboard", "#2471a3",
                "Stockout rate\nRevenue at risk\n30-day trend"),
            html.Div(style={"width": "12px"}),
            box("Ops Command Center",  "#2471a3",
                "Reorder alerts\nRegional heatmap\nDemand signals"),
            html.Div(style={"width": "12px"}),
            box("Platform & Governance", "#2471a3",
                "DLT lineage\nUnity Catalog\nPipeline health"),
            html.Div(style={"width": "12px"}),
            box("Genie Space",          "#7d3c98",
                "Natural language\nOps team queries\nNo analyst needed"),
        ], style={"display": "flex", "justifyContent": "center",
                  "flexWrap": "wrap", "gap": "4px"}),

        html.Div("↑", style={"textAlign": "center", "fontSize": "22px",
                              "color": "#bbb", "margin": "14px 0 6px 0"}),
        html.Div("Databricks App (this screen) — one URL, every audience, zero connectors",
                 style={"textAlign": "center", "fontWeight": "700",
                        "color": "#FF3621", "fontSize": "14px"}),

        html.Div([
            html.Span("Serverless compute only",               style={"marginRight": "24px"}),
            html.Span("Unity Catalog · three-part table refs", style={"marginRight": "24px"}),
            html.Span("SQL-first · Delta Lake · no pandas"),
        ], style={"marginTop": "44px", "color": "#aaa", "fontSize": "11px",
                  "textAlign": "center", "borderTop": "1px solid #eee", "paddingTop": "18px"}),

    ], style={"padding": "40px 64px", "overflowY": "auto", "height": "100%",
              "boxSizing": "border-box"})


# ── Nav items ──────────────────────────────────────────────────────────────────
NAV_ITEMS = {
    **DASHBOARDS,
    "operations": {
        "label":    "Operations Command Center",
        "audience": "VP of Engineering — reorder alerts, regional heatmap, demand signals",
    },
    "architecture": {
        "label":    "Solution Architecture",
        "audience": "All personas — end-to-end platform view",
    },
}

# ── App layout ─────────────────────────────────────────────────────────────────
app    = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server

HEADER_H  = "64px"
NAV_H     = "52px"
CONTENT_H = f"calc(100vh - {HEADER_H} - {NAV_H})"

BTN_BASE = {
    "padding": "8px 18px", "cursor": "pointer", "borderRadius": "4px",
    "fontSize": "13px", "fontWeight": "600", "transition": "all 0.15s",
    "border": "1.5px solid #FF3621", "background": "#fff", "color": "#FF3621",
    "marginRight": "6px",
}

app.layout = html.Div([
    html.Div([
        html.Div([
            html.H2("Retail Replenishment Intelligence",
                    style={"color": "#FF3621", "margin": "0", "fontSize": "18px"}),
            html.P("800-Store Demand Signal Platform · Powered by Databricks",
                   style={"color": "#666", "margin": "2px 0 0 0", "fontSize": "12px"}),
        ]),
    ], style={"height": HEADER_H, "padding": "0 32px", "display": "flex",
              "alignItems": "center", "borderBottom": "1px solid #e0e0e0",
              "background": "#fff", "boxSizing": "border-box"}),

    html.Div([
        html.Div([
            html.Button(v["label"], id=f"btn-{k}", n_clicks=0, style=BTN_BASE)
            for k, v in NAV_ITEMS.items()
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div(id="audience-label",
                 style={"color": "#999", "fontSize": "12px", "fontStyle": "italic"}),
    ], style={"height": NAV_H, "padding": "0 32px", "background": "#fafafa",
              "borderBottom": "1px solid #e0e0e0", "display": "flex",
              "justifyContent": "space-between", "alignItems": "center",
              "boxSizing": "border-box"}),

    html.Div(id="tab-content", style={"height": CONTENT_H, "overflow": "hidden"}),

    dcc.Store(id="active-tab",      data="executive"),
    dcc.Store(id="reorder-rows",    data=[]),

], style={"fontFamily": "'Segoe UI', sans-serif", "height": "100vh",
          "overflow": "hidden", "background": "#fff"})


# ── Tab switch callback ────────────────────────────────────────────────────────
@app.callback(
    Output("tab-content",   "children"),
    Output("audience-label","children"),
    Output("active-tab",    "data"),
    Output("reorder-rows",  "data"),
    [Input(f"btn-{k}", "n_clicks") for k in NAV_ITEMS],
    prevent_initial_call=False,
)
def switch_tab(*_args):
    ctx    = callback_context
    active = "executive"
    if ctx.triggered and ctx.triggered[0]["prop_id"] != ".":
        active = ctx.triggered[0]["prop_id"].replace("btn-", "").replace(".n_clicks", "")

    rows = []
    if active == "architecture":
        content = architecture_layout()
    elif active == "operations":
        try:
            rows = fetch_reorder_alerts()
        except Exception:
            rows = []
        content = operations_layout(rows)
    else:
        content = html.Iframe(
            src=DASHBOARDS[active]["url"],
            style={"width": "100%", "height": "100%", "border": "none"},
        )

    return content, NAV_ITEMS[active]["audience"], active, rows


# ── Order button callback ──────────────────────────────────────────────────────
@app.callback(
    Output("order-toast", "children"),
    Input({"type": "order-btn", "index": ALL}, "n_clicks"),
    State("reorder-rows", "data"),
    prevent_initial_call=True,
)
def handle_order(n_clicks_list, rows):
    if not any(n_clicks_list):
        return dash.no_update

    triggered = callback_context.triggered_id
    if not triggered:
        return dash.no_update

    btn_key = triggered["index"]          # "store_id|sku_id"
    store_id, sku_id = btn_key.split("|", 1)

    row = next(
        (r for r in rows if str(r["store_id"]) == store_id and str(r["sku_id"]) == sku_id),
        None,
    )
    if row:
        send_order_email(row)

    return html.Div([
        html.Span("Purchase order sent", style={"fontWeight": "700"}),
        html.Span(f" — SKU {sku_id} at Store {store_id}",
                  style={"marginLeft": "6px"}),
    ], style={
        "background": "#eafaf1", "border": "1px solid #27ae60",
        "borderRadius": "6px", "padding": "10px 16px",
        "color": "#1e8449", "fontSize": "13px",
        "display": "inline-block",
    })


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
