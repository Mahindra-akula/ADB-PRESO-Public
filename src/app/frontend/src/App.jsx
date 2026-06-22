import { useState, useEffect } from 'react'
import Executive from './components/Executive'
import Operations from './components/Operations'
import Platform from './components/Platform'
import Architecture from './components/Architecture'

const TABS = [
  { key: 'executive',    label: 'Executive Overview',        sub: 'Business Leader — stockout rate, revenue at risk' },
  { key: 'operations',   label: 'Operations Command Center', sub: 'VP of Engineering — reorder alerts, regional view' },
  { key: 'platform',     label: 'Platform & Governance',     sub: 'CTO — pipeline health, data quality' },
  { key: 'architecture', label: 'Solution Architecture',     sub: 'All personas — end-to-end platform view' },
]

const DB_RED   = '#FF3621'
const HEADER_H = 64
const NAV_H    = 52

export default function App() {
  const [active, setActive] = useState('executive')

  // All data fetched once at mount — never re-fetches on tab switch
  const [regional,  setRegional]  = useState(null)
  const [alerts,    setAlerts]    = useState(null)
  const [cats,      setCats]      = useState(null)
  const [platform,  setPlatform]  = useState(null)
  const [errors,    setErrors]    = useState({})

  useEffect(() => {
    const load = (url, setter, key) =>
      fetch(url)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
        .then(setter)
        .catch(e => setErrors(prev => ({ ...prev, [key]: e.message })))

    load('/api/regional',       setRegional, 'regional')
    load('/api/top-alerts',     setAlerts,   'alerts')
    load('/api/categories',     setCats,     'cats')
    load('/api/platform-stats', setPlatform, 'platform')
  }, [])  // empty dep array — runs once only

  const current = TABS.find(t => t.key === active)

  return (
    <div style={{ fontFamily: "'Segoe UI', system-ui, sans-serif", height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ height: HEADER_H, padding: '0 32px', display: 'flex', alignItems: 'center', borderBottom: '1px solid #e0e0e0', background: '#fff', flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: DB_RED }}>Retail Replenishment Intelligence</div>
          <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>800-Store Demand Signal Platform · Powered by Databricks</div>
        </div>
      </div>

      {/* Nav */}
      <div style={{ height: NAV_H, padding: '0 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#fafafa', borderBottom: '1px solid #e0e0e0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setActive(t.key)} style={{
              padding: '7px 18px', cursor: 'pointer', borderRadius: 4, fontSize: 13, fontWeight: 600,
              border: `1.5px solid ${DB_RED}`,
              background: active === t.key ? DB_RED : '#fff',
              color:      active === t.key ? '#fff' : DB_RED,
              transition: 'all 0.15s',
            }}>
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 12, color: '#999', fontStyle: 'italic' }}>{current?.sub}</div>
      </div>

      {/* Content — all tabs rendered but only active one visible, so state is preserved */}
      <div style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
        <div style={{ display: active === 'executive'    ? 'block' : 'none', height: '100%' }}><Executive /></div>
        <div style={{ display: active === 'operations'   ? 'block' : 'none', height: '100%' }}><Operations alerts={alerts} regional={regional} cats={cats} error={errors.alerts || errors.regional} /></div>
        <div style={{ display: active === 'platform'     ? 'block' : 'none', height: '100%' }}><Platform   data={platform} error={errors.platform} /></div>
        <div style={{ display: active === 'architecture' ? 'block' : 'none', height: '100%' }}><Architecture /></div>
      </div>

    </div>
  )
}
