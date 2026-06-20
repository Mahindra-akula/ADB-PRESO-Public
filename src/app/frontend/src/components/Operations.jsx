import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export default function Operations() {
  const [alerts,   setAlerts]   = useState(null)
  const [regional, setRegional] = useState(null)
  const [cats,     setCats]     = useState(null)
  const [err,      setErr]      = useState(null)
  const [ordered,  setOrdered]  = useState({})

  useEffect(() => {
    Promise.all([
      fetch('/api/top-alerts').then(r => r.json()),
      fetch('/api/regional').then(r => r.json()),
      fetch('/api/categories').then(r => r.json()),
    ]).then(([a, r, c]) => { setAlerts(a); setRegional(r); setCats(c) }).catch(setErr)
  }, [])

  if (err)    return <div style={{ padding: 40, color: '#e74c3c' }}>Error: {err.message}</div>
  if (!alerts) return <div style={{ padding: 40, color: '#888' }}>Loading data from Databricks...</div>

  const STATUS_COLOR = { 'REORDER NOW': '#e74c3c', 'WATCH': '#f39c12', 'OK': '#27ae60' }

  function handleOrder(row) {
    const key = `${row.store_id}|${row.sku_id}`
    setOrdered(prev => ({ ...prev, [key]: 'sending' }))
    fetch('/api/order-sku', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        store_id: String(row.store_id),
        sku_id: String(row.sku_id),
        region: row.region ?? '',
        category: row.category ?? '',
        days_of_supply: Number(row.days_of_supply),
        inventory_on_hand: Number(row.inventory_on_hand),
        avg_daily_demand_7d: Number(row.avg_daily_demand_7d),
      }),
    })
      .then(() => setOrdered(prev => ({ ...prev, [key]: 'sent' })))
      .catch(() => setOrdered(prev => ({ ...prev, [key]: 'error' })))
  }

  return (
    <div style={{ padding: '32px 48px' }}>
      <div style={{ display: 'flex', gap: 32, marginBottom: 32 }}>

        {/* Regional stacked bar */}
        <div style={{ flex: 1, background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>Stockout Status by Region</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={regional} margin={{ left: 10 }}>
              <XAxis dataKey="region" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="REORDER NOW" stackId="a" fill="#e74c3c" />
              <Bar dataKey="WATCH"       stackId="a" fill="#f39c12" />
              <Bar dataKey="OK"          stackId="a" fill="#27ae60" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Top categories */}
        <div style={{ flex: 1, background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <div style={{ fontWeight: 600, marginBottom: 16 }}>At-Risk Stores by Category</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={cats} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" />
              <YAxis type="category" dataKey="category" width={100} />
              <Tooltip formatter={v => [v, 'Stores at risk']} />
              <Bar dataKey="stores_at_risk" fill="#e74c3c" radius={[0,4,4,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Alert table */}
      <div style={{ background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
        <div style={{ fontWeight: 600, marginBottom: 16 }}>Top Reorder Alerts — Most Urgent First</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              {['Region', 'Store', 'SKU', 'Category', 'Days of Supply', 'Inventory', 'Avg Daily Demand', ''].map(h => (
                <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600, color: '#555' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alerts.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #f0f0f0', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                <td style={{ padding: '9px 12px' }}>{row.region}</td>
                <td style={{ padding: '9px 12px', fontFamily: 'monospace' }}>{row.store_id}</td>
                <td style={{ padding: '9px 12px', fontFamily: 'monospace' }}>{row.sku_id}</td>
                <td style={{ padding: '9px 12px' }}>{row.category}</td>
                <td style={{ padding: '9px 12px' }}>
                  <span style={{ background: row.days_of_supply < 1 ? '#fdecea' : '#fff8e1', color: row.days_of_supply < 1 ? '#c0392b' : '#e67e22', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
                    {row.days_of_supply}d
                  </span>
                </td>
                <td style={{ padding: '9px 12px' }}>{row.inventory_on_hand}</td>
                <td style={{ padding: '9px 12px' }}>{row.avg_daily_demand_7d}</td>
                <td style={{ padding: '9px 12px' }}>
                  {(() => {
                    const key = `${row.store_id}|${row.sku_id}`
                    const state = ordered[key]
                    if (state === 'sent') return <span style={{ color: '#27ae60', fontWeight: 600, fontSize: 12 }}>✓ Ordered</span>
                    if (state === 'error') return <span style={{ color: '#e74c3c', fontSize: 12 }}>Failed</span>
                    return (
                      <button
                        onClick={() => handleOrder(row)}
                        disabled={state === 'sending'}
                        style={{
                          background: state === 'sending' ? '#ccc' : '#FF3621',
                          color: '#fff', border: 'none', borderRadius: 4,
                          padding: '5px 12px', cursor: state === 'sending' ? 'default' : 'pointer',
                          fontSize: 12, fontWeight: 700,
                        }}
                      >
                        {state === 'sending' ? 'Sending…' : 'Order Now'}
                      </button>
                    )
                  })()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
