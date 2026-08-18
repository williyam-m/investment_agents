import { useState, useRef, useEffect, useCallback } from 'react'
import DebateForm from './components/DebateForm.jsx'
import LiveFeed from './components/LiveFeed.jsx'
import CommitteeMemo from './components/CommitteeMemo.jsx'
import BudgetBar from './components/BudgetBar.jsx'
import StatusBar from './components/StatusBar.jsx'
import HistoryPanel from './components/HistoryPanel.jsx'

const API_BASE = '/api/v1'

const AGENT_NAMES = [
  '📊 Value Investor',
  '📈 Momentum Trader',
  '⚠️ Risk Analyst',
  '🌍 Macro Economist',
  '🔄 Contrarian',
]

export default function App() {
  const [status, setStatus]               = useState('idle')
  const [events, setEvents]               = useState([])
  const [memo, setMemo]                   = useState(null)
  const [budget, setBudget]               = useState({ total: 40000, used: 0, remaining: 40000 })
  const [currentRound, setCurrentRound]   = useState(0)
  const [maxRounds, setMaxRounds]         = useState(3)
  const [error, setError]                 = useState(null)
  const [debating, setDebating]           = useState(false)
  const [agentThinking, setAgentThinking] = useState([])
  const [darkMode, setDarkMode]           = useState(() => {
    try { return localStorage.getItem('darkMode') === 'true' } catch { return false }
  })
  const [showHistory, setShowHistory]     = useState(false)
  const [history, setHistory]             = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const eventSourceRef   = useRef(null)
  const thinkingTimerRef = useRef(null)
  const bottomRef        = useRef(null)

  // ── Dark mode ────────────────────────────────────────────────────────────
  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    try { localStorage.setItem('darkMode', darkMode) } catch {}
  }, [darkMode])

  // ── Thinking cycle ───────────────────────────────────────────────────────
  function startThinkingCycle() {
    setAgentThinking(AGENT_NAMES.slice(0, 3))
    let idx = 0
    thinkingTimerRef.current = setInterval(() => {
      idx = (idx + 1) % AGENT_NAMES.length
      setAgentThinking(
        AGENT_NAMES.slice(idx, idx + 3).concat(
          idx + 3 > AGENT_NAMES.length ? AGENT_NAMES.slice(0, (idx + 3) % AGENT_NAMES.length) : []
        )
      )
    }, 1800)
  }

  function stopThinkingCycle() {
    if (thinkingTimerRef.current) {
      clearInterval(thinkingTimerRef.current)
      thinkingTimerRef.current = null
    }
    setAgentThinking([])
    setDebating(false)
  }

  // ── Auto-scroll to bottom ────────────────────────────────────────────────
  useEffect(() => {
    if (status === 'running' || memo) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, memo, status])

  // ── History ──────────────────────────────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const resp = await fetch(`${API_BASE}/debates`)
      if (resp.ok) {
        const data = await resp.json()
        setHistory(data)
      }
    } catch {}
    setHistoryLoading(false)
  }, [])

  // Fetch history when panel opens, and also on mount so count is ready
  useEffect(() => {
    fetchHistory()
  }, [])                              // on mount

  useEffect(() => {
    if (showHistory) fetchHistory()
  }, [showHistory, fetchHistory])

  async function handleDeleteDebate(debate_id) {
    try {
      await fetch(`${API_BASE}/debates/${debate_id}`, { method: 'DELETE' })
      setHistory(h => h.filter(d => d.debate_id !== debate_id))
    } catch {}
  }

  async function handleLoadDebate(debate_id) {
    try {
      const resp = await fetch(`${API_BASE}/debates/${debate_id}`)
      if (!resp.ok) return
      const data = await resp.json()
      // Reset state and show the loaded debate
      setEvents([])
      setError(null)
      setCurrentRound(data.total_rounds_completed ?? 0)
      setMaxRounds(data.total_rounds_completed ?? 0)
      if (data.committee_memo) setMemo(data.committee_memo)
      if (data.rounds) {
        const fakeEvents = []
        data.rounds.forEach(round => {
          ;(round.agent_outputs || []).forEach(output => {
            fakeEvents.push({ type: 'agent_output', data: output })
          })
        })
        setEvents(fakeEvents)
      }
      if (data.budget_summary) {
        const bs = data.budget_summary
        const total = bs.total_allocated ?? 40000
        const used  = bs.total_used ?? 0
        setBudget({ total, used, remaining: total - used })
      }
      setStatus('complete')
      setShowHistory(false)
    } catch {}
  }

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit(formData) {
    setStatus('running')
    setEvents([])
    setMemo(null)
    setError(null)
    setCurrentRound(1)
    setMaxRounds(formData.rounds)
    setDebating(true)
    setBudget({ total: formData.budget, used: 0, remaining: formData.budget })
    startThinkingCycle()

    try {
      const resp = await fetch(`${API_BASE}/debates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thesis: formData.thesis,
          investment_context: { ticker: formData.ticker || null },
          total_budget: formData.budget,
          max_rounds: formData.rounds,
          model_config: { model: formData.model },
        }),
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Debate failed' }))
        throw new Error(err.detail || 'Debate failed')
      }

      const data = await resp.json()

      // ── Async mode: server started debate → stream SSE ──
      if (data.debate_id && data.status === 'started') {
        streamEvents(data.debate_id, formData)
        return
      }

      // ── Sync mode: full response returned immediately ──
      stopThinkingCycle()

      if (data.committee_memo) setMemo(data.committee_memo)

      if (data.rounds) {
        const fakeEvents = []
        data.rounds.forEach(round => {
          ;(round.agent_outputs || []).forEach(output => {
            fakeEvents.push({ type: 'agent_output', data: output })
          })
        })
        setEvents(fakeEvents)
      }

      if (data.budget_summary) {
        const bs = data.budget_summary
        const total = bs.total_allocated ?? formData.budget
        const used  = bs.total_used ?? 0
        setBudget({ total, used, remaining: total - used })
      }

      setStatus('complete')
      fetchHistory()
    } catch (e) {
      stopThinkingCycle()
      setError(e.message)
      setStatus('error')
    }
  }

  // ── SSE streaming ──────────────────────────────────────────────────────────
  function streamEvents(debateId, formData) {
    if (eventSourceRef.current) eventSourceRef.current.close()

    const es = new EventSource(`${API_BASE}/debates/${debateId}/stream`)
    eventSourceRef.current = es

    es.addEventListener('agent_output', e => {
      const d = JSON.parse(e.data)
      setEvents(prev => [...prev, { type: 'agent_output', data: d }])
      stopThinkingCycle()
    })

    es.addEventListener('round_started', e => {
      const d = JSON.parse(e.data)
      setCurrentRound(d.round_number ?? 1)
    })

    es.addEventListener('budget_update', e => {
      const d = JSON.parse(e.data)
      if (d.budget) {
        setBudget({
          total:     d.budget.total_budget ?? formData.budget,
          used:      d.budget.total_used   ?? 0,
          remaining: d.budget.remaining    ?? 0,
        })
      }
    })

    es.addEventListener('synthesis_complete', e => {
      const d = JSON.parse(e.data)
      if (d.committee_memo) setMemo(d.committee_memo)
      stopThinkingCycle()
      setStatus('complete')
      es.close()
      fetchHistory()
    })

    es.addEventListener('debate_complete', e => {
      const d = JSON.parse(e.data)
      if (d.committee_memo) setMemo(d.committee_memo)
      stopThinkingCycle()
      setStatus('complete')
      es.close()
      fetchHistory()
    })

    es.onerror = () => {
      setStatus(s => (s === 'running' ? 'complete' : s))
      stopThinkingCycle()
      es.close()
      fetchHistory()
    }
  }

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close()
      if (thinkingTimerRef.current) clearInterval(thinkingTimerRef.current)
    }
  }, [])

  const hasContent = events.length > 0 || memo || (status === 'running' && debating)

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-left">
          <div className="header-logo">
            <div className="header-logo-icon">🏛️</div>
            <h1>Investment Committee</h1>
          </div>
          <div className="header-divider" />
          <span className="header-badge">
            <span className="header-badge-dot" />
            AI Committee
          </span>
        </div>
        <div className="header-right">
          <span className="header-meta">5 analysts · Multi-round debate</span>

          {/* History button */}
          <button
            className="icon-btn"
            onClick={() => { setShowHistory(h => !h) }}
            title="View debate history"
            aria-label="History"
          >
            🕐 History
          </button>

          {/* Dark mode toggle */}
          <button
            className="icon-btn icon-btn-round"
            onClick={() => setDarkMode(d => !d)}
            title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle dark mode"
          >
            {darkMode ? '☀️' : '🌙'}
          </button>
        </div>
      </header>

      {/* ── History panel (slide-in overlay) ── */}
      {showHistory && (
        <HistoryPanel
          history={history}
          loading={historyLoading}
          onClose={() => setShowHistory(false)}
          onLoad={handleLoadDebate}
          onDelete={handleDeleteDebate}
          onRefresh={fetchHistory}
        />
      )}

      {/* ── Chat window (single centred column) ── */}
      <main className="chat-main">
        <div className="chat-column">

          {/* Input area — always at top */}
          <div className="chat-form-area">
            <DebateForm
              onSubmit={handleSubmit}
              disabled={status === 'running'}
              loading={debating}
            />
          </div>

          {/* Status + Budget inline row (only when active) */}
          {status !== 'idle' && (
            <div className="chat-meta-row">
              <StatusBar
                status={status}
                currentRound={currentRound}
                maxRounds={maxRounds}
                error={error}
              />
              <BudgetBar
                total={budget.total}
                used={budget.used}
                remaining={budget.remaining}
              />
            </div>
          )}

          {/* Output area — grows downward */}
          <div className="chat-output">
            {!hasContent && (
              <div className="empty-state">
                <div className="empty-state-icon">📊</div>
                <h3>No debate running</h3>
                <p>Enter an investment thesis above and click <strong>Start</strong> to begin the committee debate.</p>
              </div>
            )}

            {(events.length > 0 || (status === 'running' && debating)) && (
              <LiveFeed
                events={events}
                status={status}
                debating={debating}
                agentThinking={agentThinking}
              />
            )}

            {memo && <CommitteeMemo memo={memo} />}

            {/* Scroll anchor */}
            <div ref={bottomRef} style={{ height: 1 }} />
          </div>

        </div>
      </main>
    </div>
  )
}
