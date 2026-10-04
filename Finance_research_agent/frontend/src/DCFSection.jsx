import { useState } from 'react'

export default function DCFSection() {
  const [ticker, setTicker] = useState('')
  const [wacc, setWacc] = useState('')
  const [terminalGrowth, setTerminalGrowth] = useState('')
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

    const body = {
      ticker: ticker.trim().toUpperCase(),
    }
    if (wacc) body.wacc = parseFloat(wacc)
    if (terminalGrowth) body.terminal_growth = parseFloat(terminalGrowth) / 100

    try {
      const res = await fetch('/api/valuation/dcf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'DCF calculation failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fmt = (n) => {
    if (n == null || isNaN(n)) return '—'
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + 'B'
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K'
    return n.toFixed(2)
  }

  const fmtPct = (n) => (n != null ? (n * 100).toFixed(2) + '%' : '—')

  return (
    <div className="section">
      <div className="section-header">
        <h2>DCF Valuation</h2>
        <p>Discounted Cash Flow analysis with sensitivity matrix</p>
      </div>

      <form onSubmit={handleSubmit} className="dcf-form">
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
            <span>WACC (optional)</span>
            <input
              type="number"
              step="0.01"
              placeholder="Auto"
              value={wacc}
              onChange={(e) => setWacc(e.target.value)}
            />
          </label>

          <label className="field">
            <span>Terminal Growth % (optional)</span>
            <input
              type="number"
              step="0.1"
              placeholder="3"
              value={terminalGrowth}
              onChange={(e) => setTerminalGrowth(e.target.value)}
            />
          </label>
        </div>

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? '⏳ Calculating...' : '🧮 Run DCF'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {result && (
        <div className="results-card">
          <div className="result-title">{result.ticker}</div>

          <div className="metric-grid">
            <div className="metric highlight">
              <div className="metric-label">Implied Price</div>
              <div className="metric-value">${result.implied_price?.toFixed(2)}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Enterprise Value</div>
              <div className="metric-value">${fmt(result.enterprise_value)}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Equity Value</div>
              <div className="metric-value">${fmt(result.equity_value)}</div>
            </div>
            <div className="metric">
              <div className="metric-label">WACC</div>
              <div className="metric-value">{fmtPct(result.wacc)}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Terminal Growth</div>
              <div className="metric-value">{fmtPct(result.terminal_growth)}</div>
            </div>
          </div>

          {result.assumptions && Object.keys(result.assumptions).length > 0 && (
            <div className="assumptions-block">
              <h3>Assumptions</h3>
              <table className="data-table">
                <thead>
                  <tr><th>Parameter</th><th>Value</th></tr>
                </thead>
                <tbody>
                  {Object.entries(result.assumptions).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k.replace(/_/g, ' ')}</td>
                      <td>{typeof v === 'number' ? v.toFixed(4) : String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.warnings?.length > 0 && (
            <div className="warnings-block">
              <h3>⚠️ Warnings</h3>
              <ul>
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          {result.sensitivity && result.sensitivity.implied_prices && (
            <div className="sensitivity-block">
              <h3>Sensitivity Matrix (Growth × WACC → Implied Price)</h3>
              <SensitivityTable sensitivity={result.sensitivity} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SensitivityTable({ sensitivity }) {
  const { wacc_values, growth_values, implied_prices, base_wacc, base_growth } = sensitivity

  return (
    <table className="sensitivity-table">
      <thead>
        <tr>
          <th>Growth ↓ / WACC →</th>
          {wacc_values.map((w, i) => (
            <th key={i} className={w === base_wacc ? 'base' : ''}>
              {(w * 100).toFixed(1)}%
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {growth_values.map((g, ri) => (
          <tr key={ri}>
            <th className={g === base_growth ? 'base' : ''}>
              {(g * 100).toFixed(1)}%
            </th>
            {implied_prices[ri]?.map((v, ci) => (
              <td key={ci} className={`${wacc_values[ci] === base_wacc && g === base_growth ? 'base' : ''}`}>
                ${typeof v === 'number' ? v.toFixed(2) : '—'}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
