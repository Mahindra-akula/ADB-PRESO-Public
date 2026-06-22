export default function Architecture() {
  const DB_RED = '#FF3621'

  const Box = ({ label, color, detail }) => (
    <div style={{ background: color, borderRadius: 8, padding: '16px 20px', minWidth: 160, textAlign: 'center', color: '#fff', flexShrink: 0 }}>
      <div style={{ fontWeight: 700, fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 11, opacity: 0.8, marginTop: 6, lineHeight: 1.5, whiteSpace: 'pre-line' }}>{detail}</div>
    </div>
  )

  const Arrow = () => (
    <div style={{ fontSize: 22, color: '#bbb', alignSelf: 'center', padding: '0 8px', flexShrink: 0 }}>→</div>
  )

  return (
    <div style={{ padding: '40px 64px', overflowY: 'auto' }}>
      <h2 style={{ color: '#1a1a1a', marginBottom: 4, fontSize: 22 }}>Solution Architecture</h2>
      <p style={{ color: '#777', marginBottom: 40, fontSize: 13 }}>Retail Replenishment Intelligence · Databricks Free Edition · Serverless</p>

      {/* Pipeline row */}
      <div style={{ display: 'flex', alignItems: 'stretch', justifyContent: 'center', flexWrap: 'wrap', gap: 4, marginBottom: 40 }}>
        <Box label="POS Transactions"  color="#3d3d3d" detail={'100 stores · 50 SKUs\n150K rows / 30 days\n(scales to 800 stores)'} />
        <Arrow />
        <Box label="Bronze"            color="#c0392b" detail={'Raw ingestion\nDelta Live Tables\nAuto Loader ready'} />
        <Arrow />
        <Box label="Silver"            color="#d35400" detail={'Deduped + typed\n7 & 14-day rolling\ndemand signals'} />
        <Arrow />
        <Box label="Gold"              color="#27ae60" detail={'Replenishment signals\nDays of supply\nREORDER NOW / WATCH / OK'} />
      </div>

      {/* Down arrow */}
      <div style={{ textAlign: 'center', fontSize: 22, color: '#bbb', marginBottom: 16 }}>↓</div>

      {/* Presentation layer */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <Box label="Executive Overview"      color="#2471a3" detail={'Stockout rate\nRevenue at risk\nStatus distribution'} />
        <Box label="Ops Command Center"      color="#2471a3" detail={'Reorder alerts\nRegional heatmap\nCategory risks'} />
        <Box label="Platform & Governance"   color="#2471a3" detail={'Pipeline health\nUnity Catalog\nData quality'} />
        <Box label="Genie Space"             color="#7d3c98" detail={'Natural language\nOps team queries\nNo analyst needed'} />
      </div>

    </div>
  )
}
