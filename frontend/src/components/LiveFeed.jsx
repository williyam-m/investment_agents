import { useEffect, useRef } from 'react'

const AGENT_LABELS = {
  value_investor:   '📊 Value Investor',
  momentum_trader:  '📈 Momentum Trader',
  risk_analyst:     '⚠️ Risk Analyst',
  macro_economist:  '🌍 Macro Economist',
  contrarian:       '🔄 Contrarian',
  tiebreaker:       '⚖️ Tiebreaker',
  synthesis:        '📋 Synthesis',
}

function recLabel(rec) {
  return (rec || 'N/A').replace(/_/g, ' ').toUpperCase()
}

function ThinkingCard({ name }) {
  return (
    <div className="thinking-card">
      <div className="thinking-dots">
        <span className="thinking-dot" />
        <span className="thinking-dot" />
        <span className="thinking-dot" />
      </div>
      <div className="thinking-content">
        <div className="thinking-name">{name}</div>
        <div className="thinking-text">Analyzing thesis…</div>
      </div>
    </div>
  )
}

export default function LiveFeed({ events, status, debating, agentThinking = [] }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, agentThinking])

  const agentEvents = events.filter(e => e.type === 'agent_output')

  // Group events by round
  const rounds = {}
  agentEvents.forEach(event => {
    const rn = event.data.round_number ?? 1
    if (!rounds[rn]) rounds[rn] = []
    rounds[rn].push(event)
  })
  const roundNumbers = Object.keys(rounds).map(Number).sort((a, b) => a - b)

  const showThinking = status === 'running' && debating && agentEvents.length === 0

  return (
    <div className="live-feed-wrapper">
      {/* Header */}
      <div className="live-feed-header">
        {status === 'running' && <span className="live-dot" />}
        <span className="live-feed-title">
          {status === 'running' ? 'Live Debate Feed' : 'Debate Feed'}
        </span>
        {agentEvents.length > 0 && (
          <span className="event-count">{agentEvents.length} outputs</span>
        )}
      </div>

      <div className="live-feed-container">

        {/* ── Thinking skeleton ── */}
        {showThinking && agentThinking.length > 0 && (
          <>
            <div className="round-divider">Round 1 · Agents deliberating</div>
            {agentThinking.map((name, i) => (
              <ThinkingCard key={`${name}-${i}`} name={name} />
            ))}
          </>
        )}

        {/* ── Real events grouped by round ── */}
        {roundNumbers.map(rn => (
          <div key={rn}>
            <div className="round-divider">Round {rn}</div>

            {rounds[rn].map((event, idx) => {
              const d = event.data
              const rec = (d.recommendation || 'hold').toLowerCase().replace(/ /g, '_')
              const conviction = Math.min(1, Math.max(0, d.conviction_score ?? 0))

              return (
                <div
                  key={idx}
                  className={`agent-card ${rec}`}
                >
                  {/* Header */}
                  <div className="agent-card-header">
                    <span className="agent-name">
                      {AGENT_LABELS[d.agent_type] || d.agent_type}
                    </span>
                    <div className="agent-card-meta">
                      {d.recommendation && (
                        <span className={`rec-badge rec-${rec}`}>
                          {recLabel(d.recommendation)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Conviction bar */}
                  <div className="conviction-row">
                    <span className="conviction-label">Conviction</span>
                    <div className="bar-track">
                      <div className={`bar-fill ${rec}`} style={{ width: `${conviction * 100}%` }} />
                    </div>
                    <span className="conviction-pct">
                      {(conviction * 100).toFixed(0)}%
                    </span>
                  </div>

                  {/* Key argument */}
                  {d.key_argument && (
                    <p className="agent-argument">{d.key_argument}</p>
                  )}
                </div>
              )
            })}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
