
const LAYER_COLOR = { Bronze: '#c0392b', Silver: '#7f8c8d', Gold: '#f39c12' }

function StatCard({ label, value, sub }) {
  return (
    <div style={{ background: '#fff', borderRadius: 8, padding: '20px 24px', flex: 1, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
      <div style={{ fontSize: 12, color: '#888', textTransform: 'uppercase', letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: '#1a1a1a', marginTop: 8 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function Platform({ data: stats, error }) {
  if (error)  return <div style={{ padding: 40, color: '#e74c3c' }}>Error: {error}</div>
  if (!stats)  return <div style={{ padding: 40, color: '#888' }}>Loading platform stats...</div>

  const totalRows = stats.tables.reduce((s, t) => s + t.rows, 0)

  return (
    <div style={{ padding: '32px 48px' }}>

      {/* KPI row */}
      <div style={{ display: 'flex', gap: 20, marginBottom: 40 }}>
        <StatCard label="Total Records Processed" value={totalRows.toLocaleString()} sub="across all pipeline layers" />
        <StatCard label="Pipeline Tables"          value={stats.tables.length}        sub="bronze · silver · gold" />
        <StatCard label="Last Signal Date"         value={stats.last_updated}         sub="gold.replenishment_signals" />
        <StatCard label="Catalog"                  value="retail_intelligence"        sub="Unity Catalog — 3-part naming" />
      </div>

      {/* Table row counts */}
      <div style={{ background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', marginBottom: 32 }}>
        <div style={{ fontWeight: 600, marginBottom: 20 }}>Medallion Pipeline — Table Row Counts</div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'stretch' }}>
          {stats.tables.map((t, i) => (
            <div key={t.table} style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ background: LAYER_COLOR[t.layer], borderRadius: 8, padding: '20px 16px', color: '#fff', marginBottom: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, opacity: 0.8 }}>{t.layer.toUpperCase()}</div>
                <div style={{ fontSize: 22, fontWeight: 700, marginTop: 8 }}>{t.rows.toLocaleString()}</div>
                <div style={{ fontSize: 10, opacity: 0.8, marginTop: 4 }}>rows</div>
              </div>
              <div style={{ fontSize: 12, color: '#555', fontFamily: 'monospace' }}>{t.table}</div>
              {i < stats.tables.length - 1 && (
                <div style={{ position: 'absolute', right: -24, top: '50%', color: '#bbb', fontSize: 20 }}>→</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Platform notes */}
      <div style={{ display: 'flex', gap: 20 }}>
        {[
          { title: 'Compute', body: 'Serverless only — zero cluster management, pay per query. No i3.xlarge, no spark_version pinning.' },
          { title: 'Governance', body: 'Unity Catalog — all tables referenced as retail_intelligence.retail_data.table. One-click lineage.' },
          { title: 'Streaming-Ready', body: 'DLT pipeline switches from batch to streaming with one line change: spark.read → spark.readStream in the bronze layer.' },
          { title: 'Open Format', body: 'Delta Lake files in Unity Catalog Volumes. Readable by any engine — no vendor lock-in on storage.' },
        ].map(n => (
          <div key={n.title} style={{ flex: 1, background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#FF3621', marginBottom: 8 }}>{n.title}</div>
            <div style={{ fontSize: 13, color: '#555', lineHeight: 1.6 }}>{n.body}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
