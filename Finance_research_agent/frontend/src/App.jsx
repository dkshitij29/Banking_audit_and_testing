import { useState, useEffect } from 'react'
import UploadSection from './UploadSection'
import DCFSection from './DCFSection'
import CompsSection from './CompsSection'

export default function App() {
  const [tab, setTab] = useState('upload')
  const [health, setHealth] = useState(null)
  const [loadingHealth, setLoadingHealth] = useState(true)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setHealth(d))
      .catch(() => setHealth({ status: 'error' }))
      .finally(() => setLoadingHealth(false))
  }, [])

  const tabs = [
    { id: 'upload', label: 'Upload Filing', icon: '📄' },
    { id: 'dcf', label: 'DCF Valuation', icon: '📊' },
    { id: 'comps', label: 'Peer Comps', icon: '📈' },
  ]

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>Finance Research Agent</h1>
          <span className="subtitle">SEC filings, DCF valuation & peer comps</span>
        </div>
        <div className="header-right">
          {loadingHealth ? (
            <span className="status-badge checking">Connecting...</span>
          ) : health?.status === 'ok' ? (
            <span className="status-badge ok">● Online — {health.llm_provider}</span>
          ) : (
            <span className="status-badge error">● Offline</span>
          )}
        </div>
      </header>

      <nav className="tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === 'upload' && <UploadSection />}
        {tab === 'dcf' && <DCFSection />}
        {tab === 'comps' && <CompsSection />}
      </main>
    </div>
  )
}
