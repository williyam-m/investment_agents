const STATUS_CONFIG = {
  running: {
    label:    'Debate in progress…',
    dotClass: 'running',
    cardClass: 'running',
    color:    'var(--accent)',
  },
  complete: {
    label:    'Debate complete',
    dotClass: 'complete',
    cardClass: 'complete',
    color:    'var(--green)',
  },
  error: {
    label:    'Error occurred',
    dotClass: 'error',
    cardClass: 'error',
    color:    'var(--red)',
  },
}

export default function StatusBar({ status, currentRound, maxRounds, error }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.running

  return (
    <div className={`card status-card ${cfg.cardClass}`}>
      <div className="status-row">
        {/* Animated dot */}
        <div className="status-dot-wrap">
          <span className={`status-dot-ring ${cfg.dotClass}`} />
          <span className={`status-dot ${cfg.dotClass}`} />
        </div>

        <span className="status-label">{cfg.label}</span>

        {status === 'running' && currentRound > 0 && (
          <span className="round-badge">
            Round {currentRound}{maxRounds ? ` / ${maxRounds}` : ''}
          </span>
        )}

        {status === 'complete' && (
          <span className="round-badge" style={{
            background: 'var(--green-bg)',
            color: 'var(--green)',
            border: '1px solid rgba(26,127,75,0.25)',
          }}>
            ✓ Done
          </span>
        )}
      </div>

      {error && (
        <div className="status-error">{error}</div>
      )}
    </div>
  )
}
