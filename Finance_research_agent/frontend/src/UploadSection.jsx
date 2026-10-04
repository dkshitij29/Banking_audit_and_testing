import { useState, useRef } from 'react'

export default function UploadSection() {
  const [ticker, setTicker] = useState('')
  const [filingType, setFilingType] = useState('10-K')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file || !ticker.trim()) {
      setError('Please select a file and enter a ticker.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('ticker', ticker.trim().toUpperCase())
    formData.append('filing_type', filingType)

    try {
      const res = await fetch('/api/upload-filing', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  return (
    <div className="section">
      <div className="section-header">
        <h2>📄 Upload SEC Filing</h2>
        <p>Upload a 10-K, 10-Q, 8-K, or DEF 14A filing (PDF or HTML)</p>
      </div>

      <form onSubmit={handleSubmit} className="upload-form">
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
            <span>Filing Type</span>
            <select value={filingType} onChange={(e) => setFilingType(e.target.value)}>
              <option>10-K</option>
              <option>10-Q</option>
              <option>8-K</option>
              <option>DEF 14A</option>
            </select>
          </label>
        </div>

        <div
          className={`drop-zone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.html,.htm"
            hidden
            onChange={(e) => e.target.files[0] && setFile(e.target.files[0])}
          />
          {file ? (
            <div className="file-info">
              <span className="file-icon">📎</span>
              <div>
                <div className="file-name">{file.name}</div>
                <div className="file-size">{(file.size / 1024).toFixed(1)} KB</div>
              </div>
              <button
                type="button"
                className="remove-file"
                onClick={(e) => { e.stopPropagation(); setFile(null) }}
              >
                ✕
              </button>
            </div>
          ) : (
            <div className="drop-placeholder">
              <div className="drop-icon">📁</div>
              <div>Drop a PDF or HTML file here, or click to browse</div>
            </div>
          )}
        </div>

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? '⏳ Uploading & Parsing...' : '🚀 Upload & Parse'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}
      {result && (
        <div className="alert success">
          <strong>✓ Filing parsed successfully!</strong>
          <div className="result-details">
            <span>Filing ID: <code>{result.filing_id}</code></span>
            <span>Sections extracted: <strong>{result.sections_extracted}</strong></span>
            <span>Status: {result.status}</span>
          </div>
        </div>
      )}
    </div>
  )
}
