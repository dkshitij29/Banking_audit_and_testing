import { useState } from 'react'

export default function CompsSection() {
  const [ticker, setTicker] = useState('')
  const [peersInput, setPeersInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!ticker.trim()) {
      setError('Please enter a ticker.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const peers = peersInput
      .split(',')
      .map((p) => p.trim().toUpperCase())
      .filter(Boolean)

    try {
      const res = await fetch('/api/valuation/comps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: ticker.trim().toUpperCase(),
          peers,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Comps calculation failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="section">
      <div className="section-header">
        <h2>Peer Comparison</h2>
        <p>EV/EBITDA and P/E peer comparison analysis</p>
      </div>

      <form onSubmit={handleSubmit} className="comps-form">
        <div className="form-row">
          <label className="field">
            <span>Ticker</span>
            <input
              type="text"
              placeholder="AAPL"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              maxLength={5}
            />
          </label>

          <label className="field">
            <span>Peers (comma-separated, optional)</span>
            <input
              type="text"
              placeholder="MSFT, GOOGL, META"
              value={peersInput}
              onChange={(e) => setPeersInput(e.target.value)}
            />
          </label>
        </div>

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? '⏳ Calculating...' : '📊 Run Comps'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {result && (
        <div className="results-card">
          <div className="result-title">{result.ticker}</div>

          <div className="metric-grid">
            <div className="metric highlight">
              <div className="metric-label">Implied Median Price</div>
              <div className="metric-value">
                ${result.implied_prices?.median?.toFixed(2) ?? '—'}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Median EV/EBITDA</div>
              <div className="metric-value">
                {result.median_ev_ebitda?.toFixed(2) ?? '—'}x
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Median P/E</div>
              <div className="metric-value">
                {result.median_pe?.toFixed(2) ?? '—'}x
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">EV/EBITDA Implied</div>
              <div className="metric-value">
                ${result.implied_prices?.ev_ebitda?.toFixed(2) ?? '—'}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">P/E Implied</div>
              <div className="metric-value">
                ${result.implied_prices?.pe?.toFixed(2) ?? '—'}
              </div>
            </div>
          </div>

          {result.peers?.length > 0 && (
            <div className="peers-block">
              <h3>Peer Metrics</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>EV/EBITDA</th>
                    <th>P/E Ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {result.peers.map((p, i) => (
                    <tr key={i}>
                      <td><strong>{p.ticker}</strong></td>
                      <td>{p.ev_ebitda?.toFixed(2) ?? '—'}</td>
                      <td>{p.pe_ratio?.toFixed(2) ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
