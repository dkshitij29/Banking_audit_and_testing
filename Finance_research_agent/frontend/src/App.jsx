import { useState, useRef, useCallback, useEffect } from 'react'
import './App.css'

const US_FILING_TYPES = ['10-K', '10-Q', '8-K', 'DEF 14A']
const IN_FILING_TYPES = ['AOC-4', 'AOC-4 CFS', 'XBRL Instance', 'Combined Bundle']

export default function App() {
  const [market, setMarket] = useState('US')  // 'US' | 'IN'
  const [ticker, setTicker] = useState('')
  const [cin, setCin] = useState('')
  const [entityType, setEntityType] = useState('auto')
  const [filingType, setFilingType] = useState('10-K')
  const [files, setFiles] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [health, setHealth] = useState(null)
  const [aoc4Config, setAoc4Config] = useState(null)
  const inputRef = useRef()

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => setHealth(d))
      .catch(() => setHealth({ status: 'error' }))
  }, [])

  useEffect(() => {
    if (market === 'IN') {
      fetch('/api/aoc4/config')
        .then((r) => r.json())
        .then((d) => setAoc4Config(d))
        .catch(() => setAoc4Config({ india_config_ready: false }))
    }
    setFilingType(market === 'US' ? '10-K' : 'AOC-4')
  }, [market])

  const handleFileAdd = useCallback((newFiles) => {
    setFiles((prev) => [...prev, ...newFiles])
  }, [])

  const removeFile = useCallback((index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const allowed = market === 'US'
      ? ['.pdf', '.html', '.htm']
      : ['.pdf', '.xml', '.xbrl', '.zip', '.html', '.htm']
    const dropped = Array.from(e.dataTransfer.files).filter((f) =>
      allowed.some((ext) => f.name.toLowerCase().endsWith(ext))
    )
    handleFileAdd(dropped)
  }, [handleFileAdd, market])

  const handleInputChange = useCallback((e) => {
    if (e.target.files) {
      handleFileAdd(Array.from(e.target.files))
    }
    if (inputRef.current) inputRef.current.value = ''
  }, [handleFileAdd])

  const validateCin = (value) => {
    return /^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$/.test(value)
  }

  const handleAnalyze = async () => {
    setError(null)

    if (market === 'US') {
      if (!ticker.trim()) {
        setError('Please enter a ticker symbol.')
        return
      }
    } else {
      if (!ticker.trim() && !cin.trim()) {
        setError('Please enter a ticker or CIN.')
        return
      }
      if (cin.trim() && !validateCin(cin.trim())) {
        setError('Invalid CIN format. Expected: LU + 5 digits + 2 letters + 4 digits + 3 letters + 6 digits')
        return
      }
    }

    setIsProcessing(true)
    setResult(null)

    const formData = new FormData()

    if (market === 'US') {
      // ── US path ──────────────────────────────────────────────
      formData.append('ticker', ticker.trim().toUpperCase())
      formData.append('filing_type', filingType)
      if (files.length > 0) {
        formData.append('file', files[0])
      }

      try {
        const response = await fetch('/api/analyze', { method: 'POST', body: formData })
        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.detail || `Request failed with status ${response.status}`)
        }
        setResult(data)
      } catch (err) {
        setError(err.message || 'Something went wrong.')
      } finally {
        setIsProcessing(false)
      }
    } else {
      // ── India AOC-4 path ─────────────────────────────────────
      if (ticker.trim()) formData.append('ticker', ticker.trim().toUpperCase())
      if (cin.trim()) formData.append('cin', cin.trim())
      formData.append('entity_type', entityType)
      if (filingType) formData.append('filing_type', filingType)

      for (const file of files) {
        formData.append('files', file)
      }

      try {
        const response = await fetch('/api/aoc4/analyze', { method: 'POST', body: formData })
        const data = await response.json()
        if (!response.ok) {
          const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
          throw new Error(detail || `Request failed with status ${response.status}`)
        }
        setResult(data)
      } catch (err) {
        setError(err.message || 'Something went wrong.')
      } finally {
        setIsProcessing(false)
      }
    }
  }

  const handleReset = () => {
    setTicker('')
    setCin('')
    setFiles([])
    setResult(null)
    setError(null)
  }

  const fmt = (n) => {
    if (n == null || isNaN(n)) return '—'
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + 'B'
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K'
    return n.toFixed(2)
  }

  // ── CIN regex helper ──────────────────────────────────────────────────
  const cinValid = !cin.trim() || validateCin(cin.trim())
  const hasInput = market === 'US' ? ticker.trim() : (ticker.trim() || cin.trim())

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>Finance Research Agent</h1>
          <span className="subtitle">
            {market === 'US'
              ? '5-stage analysis — Ingest → Parse → Analyse → Model → Synthesize'
              : 'AOC-4 analysis — Bundle → Ingest → Parse → Validate → Model → Synthesize'}
          </span>
        </div>
        <div className="header-right">
          {/* Market toggle */}
          <div className="market-toggle">
            <button
              className={`toggle-btn ${market === 'US' ? 'active' : ''}`}
              onClick={() => setMarket('US')}
              disabled={isProcessing}
            >US</button>
            <button
              className={`toggle-btn ${market === 'IN' ? 'active' : ''}`}
              onClick={() => setMarket('IN')}
              disabled={isProcessing}
            >🇮🇳 India</button>
          </div>
          {health?.status === 'ok' ? (
            <span className="status-badge ok">● Online — {health.llm_provider}</span>
          ) : (
            <span className="status-badge error">● Offline</span>
          )}
          {market === 'IN' && aoc4Config && !aoc4Config.india_config_ready && (
            <span className="status-badge warn">⚠ IN config incomplete</span>
          )}
        </div>
      </header>

      {/* Input Section */}
      <div className="input-section">
        <h2>{market === 'US' ? 'Run US Analysis' : 'Run India AOC-4 Analysis'}</h2>
        <p className="input-desc">
          {market === 'US'
            ? 'Enter a ticker to run the full 5-stage research pipeline. Optionally upload an SEC filing.'
            : 'Upload AOC-4 filings (XBRL, PDF, or ZIP bundle) for an Indian company. Enter ticker (listed) or CIN (unlisted).'}
        </p>

        <div className="form-row">
          {market === 'US' ? (
            <label className="field">
              <span>Ticker *</span>
              <input
                type="text"
                placeholder="AAPL"
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                maxLength={10}
                disabled={isProcessing}
              />
            </label>
          ) : (
            <>
              <label className="field">
                <span>Ticker <small>(listed)</small></span>
                <input
                  type="text"
                  placeholder="RELIANCE"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  maxLength={20}
                  disabled={isProcessing}
                />
              </label>
              <label className="field">
                <span>CIN <small>(unlisted)</small></span>
                <input
                  type="text"
                  placeholder="U74999KA2015PTC080000"
                  value={cin}
                  onChange={(e) => setCin(e.target.value.toUpperCase())}
                  maxLength={21}
                  disabled={isProcessing}
                  className={!cinValid ? 'invalid' : ''}
                />
              </label>
              <label className="field">
                <span>Entity Type</span>
                <select value={entityType} onChange={(e) => setEntityType(e.target.value)} disabled={isProcessing}>
                  <option value="auto">Auto detect</option>
                  <option value="listed">Listed</option>
                  <option value="unlisted">Unlisted</option>
                </select>
              </label>
            </>
          )}

          <label className="field">
            <span>Filing Type</span>
            <select value={filingType} onChange={(e) => setFilingType(e.target.value)} disabled={isProcessing}>
              {(market === 'US' ? US_FILING_TYPES : IN_FILING_TYPES).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
        </div>

        {/* Drop Zone */}
        <div
          className={`drop-zone ${dragging ? 'dragging' : ''} ${files.length > 0 ? 'has-file' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept={market === 'US' ? '.pdf,.html,.htm' : '.pdf,.xml,.xbrl,.zip,.html,.htm'}
            multiple={market === 'IN'}
            onChange={handleInputChange}
            className="hidden-input"
            disabled={isProcessing}
          />
          {files.length > 0 ? (
            <div className="file-list">
              {files.map((f, i) => (
                <div className="file-chip" key={i}>
                  <span>📎 {f.name} <small>({(f.size / 1024).toFixed(0)} KB)</small></span>
                  <button
                    className="chip-remove"
                    onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                  >✕</button>
                </div>
              ))}
            </div>
          ) : (
            <div className="drop-placeholder">
              <span className="drop-icon">📄</span>
              <div>
                Drop files here or click to browse
                {market === 'IN' && <span> — multiple files / ZIP accepted</span>}
              </div>
              <div className="drop-hint">
                {market === 'US'
                  ? 'Optional — market data analysis works without it'
                  : 'PDF, XML/XBRL, or ZIP bundle (max 150 MB, 40 files)'}
              </div>
            </div>
          )}
        </div>

        {/* Buttons */}
        <div className="btn-row">
          <button
            onClick={handleAnalyze}
            disabled={isProcessing || !hasInput}
            className="btn-primary"
          >
            {isProcessing ? (
              <>
                <span className="spinner" />
                {market === 'US' ? 'Running 5-Stage Analysis...' : 'Running AOC-4 Analysis...'}
              </>
            ) : (
              <>🚀 {market === 'US' ? 'Run Full Analysis' : 'Run AOC-4 Analysis'}</>
            )}
          </button>

          {result && (
            <button onClick={handleReset} className="btn-secondary">
              Start Over
            </button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && <div className="alert error">{error}</div>}

      {/* Result */}
      {result && (
        <div className="result-area animate-in">
          <VerdictCard result={result} fmt={fmt} market={market} />
        </div>
      )}
    </div>
  )
}

/* ─── Verdict Card ─── */

function VerdictCard({ result, fmt, market }) {
  const config = verdictStyles[result.verdict] || verdictStyles.FAIRLY_VALUED
  const [openSection, setOpenSection] = useState('reasoning')
  const isIN = market === 'IN'
  const cur = isIN ? '₹' : '$'

  return (
    <div className={`verdict-card ${config.cardClass}`}>
      {/* Verdict Banner */}
      <div className={`verdict-banner ${config.bannerClass}`}>
        <span className="verdict-icon">{config.icon}</span>
        <div>
          <p className="verdict-label">Valuation Verdict</p>
          <p className={`verdict-title ${config.titleClass}`}>{result.verdict.replace('_', ' ')}</p>
          {result.valuation_mode && (
            <span className="val-mode-badge">{result.valuation_mode.replace(/_/g, ' ').toUpperCase()}</span>
          )}
        </div>
        <div className="verdict-rating">
          <span className={`rating-badge ${
            result.rating === 'BUY' ? 'buy'
            : result.rating === 'SELL' ? 'sell'
            : result.rating === 'N/A' ? 'na'
            : 'hold'
          }`}>
            {result.rating}
          </span>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="metrics-row">
        {/* For unlisted India, show equity value instead of price/upside */}
        {result.equity_value ? (
          <>
            <MetricBox label="Equity Value (Low)" value={`${cur}${fmt(result.equity_value.low_inr)}`} />
            <MetricBox label="Equity Value (Mid)" value={`${cur}${fmt(result.equity_value.mid_inr)}`} highlight />
            <MetricBox label="Equity Value (High)" value={`${cur}${fmt(result.equity_value.high_inr)}`} />
            {result.equity_value.dlom_applied != null && (
              <MetricBox label="DLOM" value={`${(result.equity_value.dlom_applied * 100).toFixed(0)}%`} />
            )}
          </>
        ) : (
          <>
            <MetricBox label="Current Price" value={`${cur}${result.valuation.current_price?.toFixed(2) ?? '—'}`} />
            <MetricBox label="Fair Value" value={`${cur}${result.valuation.fair_value_mid?.toFixed(2) ?? '—'}`} highlight />
            <MetricBox label="Range" value={`${cur}${result.valuation.fair_value_low?.toFixed(0)} – ${cur}${result.valuation.fair_value_high?.toFixed(0)}`} />
            {result.valuation.upside_pct != null && (
              <MetricBox
                label="Upside"
                value={`${(result.valuation.upside_pct ?? 0) >= 0 ? '+' : ''}${(result.valuation.upside_pct ?? 0).toFixed(1)}%`}
                color={result.valuation.upside_pct > 0 ? 'green' : 'red'}
              />
            )}
          </>
        )}
        <MetricBox label="Confidence" value={result.valuation?.confidence ?? result.confidence ?? '—'} />
      </div>

      {/* Data Quality (India only) */}
      {result.data_quality && (
        <CollapsibleSection
          title="📊 Data Quality"
          isOpen={openSection === 'quality'}
          onToggle={() => setOpenSection(openSection === 'quality' ? null : 'quality')}
        >
          <div className="data-quality-grid">
            <div><strong>Score:</strong> {result.data_quality.score?.toUpperCase()}</div>
            <div><strong>Source:</strong> {result.data_quality.primary_source}</div>
            <div><strong>Periods:</strong> {result.data_quality.periods_available}</div>
            <div><strong>As of:</strong> {result.data_quality.data_as_of ?? '—'}</div>
            <div><strong>Staleness:</strong> {result.data_quality.staleness_days} days</div>
          </div>
          {result.data_quality.notes?.length > 0 && (
            <ul className="quality-notes">
              {result.data_quality.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </CollapsibleSection>
      )}

      {/* Period Table (India) */}
      {result.periods?.length > 0 && (
        <CollapsibleSection
          title="📅 Periods Extracted"
          isOpen={openSection === 'periods'}
          onToggle={() => setOpenSection(openSection === 'periods' ? null : 'periods')}
        >
          <table className="data-table">
            <thead>
              <tr><th>Label</th><th>Period End</th><th>Source</th><th>Basis</th><th>Framework</th></tr>
            </thead>
            <tbody>
              {result.periods.map((p, i) => (
                <tr key={i}>
                  <td>{p.label}</td>
                  <td>{p.period_end}</td>
                  <td>{p.source}</td>
                  <td>{p.basis ?? '—'}</td>
                  <td>{p.framework ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CollapsibleSection>
      )}

      {/* Documents (India) */}
      {result.documents?.length > 0 && (
        <CollapsibleSection
          title="📁 Documents"
          isOpen={openSection === 'documents'}
          onToggle={() => setOpenSection(openSection === 'documents' ? null : 'documents')}
        >
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>File</th><th>Type</th><th>Confidence</th></tr>
            </thead>
            <tbody>
              {result.documents.map((d, i) => (
                <tr key={i}>
                  <td>{d.doc_id}</td>
                  <td>{d.filename}</td>
                  <td>{d.doc_type}</td>
                  <td>{(d.confidence * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CollapsibleSection>
      )}

      {/* Validation Issues (India) */}
      {result.validation?.length > 0 && (
        <CollapsibleSection
          title="⚠️ Validation Issues"
          isOpen={openSection === 'validation'}
          onToggle={() => setOpenSection(openSection === 'validation' ? null : 'validation')}
        >
          <ul className="validation-list">
            {result.validation.map((v, i) => (
              <li key={i} className={`validation-issue ${v.severity}`}>
                <span className={`severity-badge ${v.severity}`}>{v.severity.toUpperCase()}</span>
                <strong>{v.code}:</strong> {v.message}
              </li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Reasoning */}
      <CollapsibleSection
        title="📋 Reasoning"
        isOpen={openSection === 'reasoning'}
        onToggle={() => setOpenSection(openSection === 'reasoning' ? null : 'reasoning')}
      >
        <pre className="reasoning-text">{result.reasoning}</pre>
      </CollapsibleSection>

      {/* Pipeline Stages */}
      <CollapsibleSection
        title="⚙️ Pipeline Stages"
        isOpen={openSection === 'stages'}
        onToggle={() => setOpenSection(openSection === 'stages' ? null : 'stages')}
      >
        <div className="stages-list">
          {result.stages.map((s, i) => (
            <div key={i} className="stage-row">
              <span className={`stage-dot ${s.status === 'complete' ? 'green' : s.status === 'skipped' ? 'amber' : s.status === 'error' ? 'red' : 'gray'}`} />
              <span className="stage-name">{s.stage}</span>
              <span className="stage-status">{s.status.toUpperCase()}</span>
              <span className="stage-summary">{s.summary}</span>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* Red Flags — handle both string[] (US) and object[] (India) */}
      {result.red_flags?.length > 0 && (
        <CollapsibleSection
          title="🚩 Red Flags"
          isOpen={openSection === 'flags'}
          onToggle={() => setOpenSection(openSection === 'flags' ? null : 'flags')}
        >
          <ul className="case-list flags">
            {result.red_flags.map((f, i) => (
              <li key={i}>
                {typeof f === 'string' ? f : (
                  <>
                    <span className={`flag-severity ${f.severity}`}>[{f.severity}]</span>{' '}
                    <strong>{f.title}</strong>
                    {f.evidence_quote && <em> — "{f.evidence_quote}"</em>}
                    {f.needs_review && <span className="review-badge">⚠ needs review</span>}
                  </>
                )}
              </li>
            ))}
          </ul>
        </CollapsibleSection>
      )}

      {/* Bull Case */}
      {result.bull_case?.length > 0 && (
        <CollapsibleSection
          title="🐂 Bull Case"
          isOpen={openSection === 'bull'}
          onToggle={() => setOpenSection(openSection === 'bull' ? null : 'bull')}
        >
          <ul className="case-list bull">
            {result.bull_case.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </CollapsibleSection>
      )}

      {/* Bear Case */}
      {result.bear_case?.length > 0 && (
        <CollapsibleSection
          title="🐻 Bear Case"
          isOpen={openSection === 'bear'}
          onToggle={() => setOpenSection(openSection === 'bear' ? null : 'bear')}
        >
          <ul className="case-list bear">
            {result.bear_case.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </CollapsibleSection>
      )}

      {/* DCF Assumptions */}
      {result.dcf_assumptions && Object.keys(result.dcf_assumptions).length > 0 && (
        <CollapsibleSection
          title="📐 Key Assumptions"
          isOpen={openSection === 'assumptions'}
          onToggle={() => setOpenSection(openSection === 'assumptions' ? null : 'assumptions')}
        >
          <table className="data-table">
            <thead>
              <tr><th>Parameter</th><th>Value</th></tr>
            </thead>
            <tbody>
              {Object.entries(result.dcf_assumptions).map(([k, v]) => (
                <tr key={k}>
                  <td>{k.replace(/_/g, ' ')}</td>
                  <td>{typeof v === 'number' ? v.toFixed(4) : String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CollapsibleSection>
      )}

      {/* What Would Change View */}
      {result.what_would_change?.length > 0 && (
        <CollapsibleSection
          title="🔄 What Would Change This View"
          isOpen={openSection === 'change'}
          onToggle={() => setOpenSection(openSection === 'change' ? null : 'change')}
        >
          <ul className="case-list">
            {result.what_would_change.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </CollapsibleSection>
      )}

      {/* Sources */}
      {result.sources?.length > 0 && (
        <div className="sources-row">
          <span className="sources-label">Sources:</span>
          {result.sources.map((s, i) => <span key={i} className="source-tag">{s}</span>)}
        </div>
      )}

      <div className="disclaimer">
        Disclaimer: Research support, not financial advice.
        {isIN && ' For unlisted companies, equity value depends on modelling assumptions including illiquidity discount.'}
      </div>
    </div>
  )
}

function MetricBox({ label, value, highlight, color }) {
  return (
    <div className={`metric-box ${highlight ? 'highlight' : ''} ${color === 'green' ? 'green' : ''} ${color === 'red' ? 'red' : ''}`}>
      <div className="metric-box-label">{label}</div>
      <div className="metric-box-value">{value}</div>
    </div>
  )
}

function CollapsibleSection({ title, isOpen, onToggle, children }) {
  return (
    <div className="collapsible-section">
      <button className="collapsible-header" onClick={onToggle}>
        <span className="chevron">{isOpen ? '▾' : '▸'}</span>
        {title}
      </button>
      {isOpen && <div className="collapsible-body">{children}</div>}
    </div>
  )
}

const verdictStyles = {
  UNDERVALUED: {
    icon: '📈',
    cardClass: 'card-green',
    bannerClass: 'banner-green',
    titleClass: 'text-green',
  },
  OVERVALUED: {
    icon: '📉',
    cardClass: 'card-red',
    bannerClass: 'banner-red',
    titleClass: 'text-red',
  },
  FAIRLY_VALUED: {
    icon: '⚖️',
    cardClass: 'card-blue',
    bannerClass: 'banner-blue',
    titleClass: 'text-blue',
  },
  INCONCLUSIVE: {
    icon: '❓',
    cardClass: 'card-gray',
    bannerClass: 'banner-gray',
    titleClass: 'text-gray',
  },
  NOT_APPLICABLE: {
    icon: '➖',
    cardClass: 'card-gray',
    bannerClass: 'banner-gray',
    titleClass: 'text-gray',
  },
}
