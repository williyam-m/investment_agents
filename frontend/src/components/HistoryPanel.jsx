import { useEffect } from 'react'

function statusIcon(status) {
  if (status === 'complete' || status === 'completed') return '✅'
  if (status === 'failed')  return '❌'
  if (status === 'pending') return '⏳'
  return '•'
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function HistoryPanel({ history, loading, onClose, onLoad, onDelete, onRefresh }) {
  // Close on Escape
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div className="history-backdrop" onClick={onClose} />

      {/* Panel */}
      <aside className="history-panel">
        <div className="history-panel-header">
          <span className="history-panel-title">🕐 Debate History</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button className="icon-btn" onClick={onRefresh} title="Refresh" aria-label="Refresh">
              🔄
            </button>
            <button className="icon-btn" onClick={onClose} title="Close" aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        <div className="history-list">
          {loading && (
            <div className="history-empty">Loading…</div>
          )}

          {!loading && history.length === 0 && (
            <div className="history-empty">
              <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.3 }}>🗂️</div>
              <p>No debates yet. Start one above!</p>
            </div>
          )}

          {!loading && history.map(item => (
            <div key={item.debate_id} className="history-item">
              <div className="history-item-header">
                <span className="history-status-icon" title={item.status}>
                  {statusIcon(item.status)}
                </span>
                <span className="history-date">{formatDate(item.started_at)}</span>
                {item.rounds > 0 && (
                  <span className="history-rounds">{item.rounds} rounds</span>
                )}
              </div>

              <p className="history-thesis" title={item.thesis}>
                {item.thesis}
              </p>

              {item.error && (
                <p className="history-error">{item.error}</p>
              )}

              <div className="history-item-actions">
                {(item.status === 'complete' || item.status === 'completed') && item.has_memo && (
                  <button
                    className="history-btn history-btn-load"
                    onClick={() => onLoad(item.debate_id)}
                  >
                    View Report
                  </button>
                )}
                <button
                  className="history-btn history-btn-delete"
                  onClick={() => onDelete(item.debate_id)}
                  title="Delete this debate"
                >
                  🗑 Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}
