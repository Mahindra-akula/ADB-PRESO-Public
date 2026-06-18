import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer, PieChart, Pie, Legend } from 'recharts'

const STATUS_COLOR = { 'REORDER NOW': '#e74c3c', 'WATCH': '#f39c12', 'OK': '#27ae60' }

function KPI({ label, value, sub, color }) {
  return (
    <div style={{ background: '#fff', borderRadius: 8, padding: '20px 24px', flex: 1, borderTop: `4px solid ${color}`, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
      <div style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color, marginTop: 8 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function Executive() {
  const [data, setData] = useState(null)
  const [err, setErr]   = useState(null)

  useEffect(() => {
    fetch('/api/summary').then(r => r.json()).then(setData).catch(setErr)
  }, [])

  if (err)  return <div style={{ padding: 40, color: '#e74c3c' }}>Error loading data: {err.message}</div>
  if (!data) return <div style={{ padding: 40, color: '#888' }}>Loading data from Databricks...</div>

  const reorderCount = data.status_counts.find(s => s.status === 'REORDER NOW')?.count ?? 0

  return (
    <div style={{ padding: '32px 48px' }}>
      {/* KPI tiles */}
      <div style={{ display: 'flex', gap: 20, marginBottom: 40 }}>
        <KPI label="Stockout Rate"          value={`${data.stockout_rate_pct}%`}              color="#e74c3c" sub="of store+SKU combos" />
        <KPI label="Weekly Revenue at Risk" value={`$${data.revenue_at_risk.toLocaleString()}`} color="#e67e22" sub="REORDER NOW combos × 7 days" />
        <KPI label="Stores Monitored"       value={data.total_stores}                          color="#2980b9" sub="demo slice (scales to 800)" />
        <KPI label="SKUs Tracked"           value={data.total_skus}                            color="#8e44ad" sub="high-velocity SKUs" />
      </div>

      <div style={{ display: 'flex', gap: 32 }}>
        {/* Status bar chart */}
        <div style={{ flex: 1, background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>Replenishment Status Distribution</div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.status_counts} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" tickFormatter={v => `${v}`} />
              <YAxis type="category" dataKey="status" width={110} />
              <Tooltip formatter={(v, n) => [v, 'Store+SKU combos']} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {data.status_counts.map(s => <Cell key={s.status} fill={STATUS_COLOR[s.status] ?? '#999'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Pie */}
        <div style={{ width: 280, background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>Share of Total</div>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={data.status_counts} dataKey="count" nameKey="status" cx="50%" cy="50%" outerRadius={90} label={({ status, pct }) => `${pct}%`}>
                {data.status_counts.map(s => <Cell key={s.status} fill={STATUS_COLOR[s.status] ?? '#999'} />)}
              </Pie>
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={{ marginTop: 24, padding: '16px 20px', background: '#fff3cd', borderRadius: 8, borderLeft: '4px solid #f39c12', fontSize: 13 }}>
        <strong>{reorderCount} store+SKU combos</strong> require replenishment action today. Their Excel model wouldn't surface this until Monday's report.
      </div>
    </div>
  )
}
