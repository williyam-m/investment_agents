import { useState, useRef, useEffect } from 'react'
import DebateForm from './components/DebateForm.jsx'
import LiveFeed from './components/LiveFeed.jsx'
import CommitteeMemo from './components/CommitteeMemo.jsx'
import BudgetBar from './components/BudgetBar.jsx'
import StatusBar from './components/StatusBar.jsx'

const API_BASE = '/api/v1'

const AGENT_NAMES = [
  '📊 Value Investor',
  '📈 Momentum Trader',
  '⚠️ Risk Analyst',
  '🌍 Macro Economist',
  '🔄 Contrarian',
]

export default function App() {
  const [status, setStatus]           = useState('idle')
  const [events, setEvents]           = useState([])
  const [memo, setMemo]               = useState(null)
  const [budget, setBudget]           = useState({ total: 40000, used: 0, remaining: 40000 })
  const [currentRound, setCurrentRound] = useState(0)
  const [maxRounds, setMaxRounds]     = useState(3)
  const [error, setError]             = useState(null)
  const [debating, setDebating]       = useState(false)
  const [agentThinking, setAgentThinking] = useState([])
  const eventSourceRef  = useRef(null)
  const thinkingTimerRef = useRef(null)

  // Cycle through "thinking" agent names while request is running
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

      if (data.committee_memo) {
        setMemo(data.committee_memo)
      }

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
        setBudget({
          total,
          used,
          remaining: total - used,
        })
      }

      setStatus('complete')
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
      // Once we get real events, stop the thinking animation
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
    })

    es.addEventListener('debate_complete', e => {
      const d = JSON.parse(e.data)
      if (d.committee_memo) setMemo(d.committee_memo)
      stopThinkingCycle()
      setStatus('complete')
      es.close()
    })

    es.onerror = () => {
      setStatus(s => (s === 'running' ? 'complete' : s))
      stopThinkingCycle()
      es.close()
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
        </div>
      </header>

      <main className="app-main">
        {/* ── Left panel ── */}
        <div className="left-panel">
          <DebateForm
            onSubmit={handleSubmit}
            disabled={status === 'running'}
            loading={debating}
          />

          {status !== 'idle' && (
            <StatusBar
              status={status}
              currentRound={currentRound}
              maxRounds={maxRounds}
              error={error}
            />
          )}

          {status !== 'idle' && (
            <BudgetBar
              total={budget.total}
              used={budget.used}
              remaining={budget.remaining}
            />
          )}
        </div>

        {/* ── Right panel ── */}
        <div className="right-panel">
          {!hasContent && (
            <div className="empty-state">
              <div className="empty-state-icon">📊</div>
              <h3>No debate running</h3>
              <p>Enter an investment thesis and click Start to begin the committee debate.</p>
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
        </div>
      </main>
    </div>
  )
}
