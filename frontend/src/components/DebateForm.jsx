import { useState } from 'react'

const EXAMPLE_THESES = [
  {
    short: 'Apple undervalued',
    full:  'Apple is undervalued at current P/E of 28x given its services growth trajectory and expanding margins',
  },
  {
    short: 'NVIDIA overvalued',
    full:  'NVIDIA is overvalued at 35x forward earnings as AI capex cycle peaks and competition intensifies',
  },
  {
    short: 'Tesla autonomous moat',
    full:  "Tesla's autonomous driving moat justifies a premium multiple despite near-term profitability headwinds",
  },
  {
    short: 'Microsoft AI play',
    full:  'Microsoft is the best pure-play AI infrastructure bet with Azure growth accelerating and Copilot monetization inflecting',
  },
  {
    short: 'Gold hedge',
    full:  'Gold is the optimal portfolio hedge given rising geopolitical risks, debt ceiling uncertainty, and persistent inflation above 3%',
  },
]

const MODELS = [
  { value: 'ollama/llama2:7b',         label: 'Llama 2 7B (Local)', emoji: '🦙' },
  { value: 'ollama/llama3',            label: 'Llama 3 (Local)',   emoji: '🦙' },
  { value: 'ollama/mistral',           label: 'Mistral (Local)',   emoji: '🦙' },
  { value: 'gpt-4o-mini',             label: 'GPT-4o Mini',       emoji: '🤖' },
  { value: 'gpt-4o',                  label: 'GPT-4o',            emoji: '🤖' },
  { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku',    emoji: '🌟' },
  { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet', emoji: '🌟' },
]

function formatTokens(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K tokens`
  return `${n} tokens`
}

export default function DebateForm({ onSubmit, disabled, loading }) {
  const [thesis, setThesis] = useState('')
  const [ticker, setTicker] = useState('')
  const [budget, setBudget] = useState(40000)
  const [rounds, setRounds] = useState(3)
  const [model,  setModel]  = useState('ollama/llama2:7b')

  function handleSubmit(e) {
    e.preventDefault()
    if (!thesis.trim() || disabled) return
    onSubmit({ thesis: thesis.trim(), ticker: ticker.trim(), budget, rounds, model })
  }

  const currentModel = MODELS.find(m => m.value === model)

  return (
    <div className="card">
      <div className="card-title">
        <span className="card-title-dot" style={{ background: 'var(--accent)' }} />
        New Debate
      </div>

      <form onSubmit={handleSubmit} className="debate-form">

        {/* ── Thesis ── */}
        <div className="form-group">
          <label>Investment Thesis</label>
          <textarea
            value={thesis}
            onChange={e => setThesis(e.target.value)}
            placeholder="e.g. Apple is undervalued given its services growth trajectory…"
            rows={3}
            disabled={disabled}
            required
            minLength={10}
          />

          <div className="example-pills">
            {EXAMPLE_THESES.map((t, i) => (
              <button
                key={i}
                type="button"
                className="example-pill"
                onClick={() => setThesis(t.full)}
                disabled={disabled}
                title={t.full}
              >
                {t.short}
              </button>
            ))}
          </div>
        </div>

        {/* ── Ticker + Model ── */}
        <div className="form-row">
          <div className="form-group">
            <label>Ticker (optional)</label>
            <input
              type="text"
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              placeholder="AAPL"
              disabled={disabled}
              maxLength={10}
            />
          </div>
          <div className="form-group">
            <label>
              Model &nbsp;
              {currentModel && (
                <span style={{ fontSize: 13 }}>{currentModel.emoji}</span>
              )}
            </label>
            <select value={model} onChange={e => setModel(e.target.value)} disabled={disabled}>
              {MODELS.map(m => (
                <option key={m.value} value={m.value}>
                  {m.emoji} {m.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Budget + Rounds sliders ── */}
        <div className="form-row">
          <div className="form-group">
            <label>
              Budget &nbsp;
              <span className="range-value">{formatTokens(budget)}</span>
            </label>
            <input
              type="range"
              min={10000}
              max={100000}
              step={5000}
              value={budget}
              onChange={e => setBudget(Number(e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="form-group">
            <label>
              Rounds &nbsp;
              <span className="range-value">{rounds}</span>
            </label>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={rounds}
              onChange={e => setRounds(Number(e.target.value))}
              disabled={disabled}
            />
          </div>
        </div>

        <button
          type="submit"
          className={`submit-btn${loading ? ' loading' : ''}`}
          disabled={disabled || !thesis.trim()}
        >
          {loading ? (
            <>
              <span className="spinner" />
              Debate in progress…
            </>
          ) : (
            <>
              🏛️ Start Committee Debate
            </>
          )}
        </button>
      </form>
    </div>
  )
}
