function formatK(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

export default function BudgetBar({ total, used, remaining }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0

  // Use CSS vars — black & white palette, data-colour for bar
  const fillColor = pct < 50
    ? 'var(--green)'
    : pct < 80
      ? 'var(--amber)'
      : 'var(--red)'

  const pctColor = fillColor

  return (
    <div className="budget-card">
      <div className="budget-header">
        <span className="budget-title">Token Budget</span>
        <span className="budget-pct" style={{ color: pctColor }}>
          {pct.toFixed(0)}%
        </span>
      </div>

      <div className="budget-meta">
        <div className="budget-meta-item">
          <span className="budget-meta-label">Used</span>
          <span className="budget-meta-value" style={{ color: pctColor }}>
            {formatK(used)}
          </span>
        </div>
        <div className="budget-meta-item">
          <span className="budget-meta-label">Remaining</span>
          <span className="budget-meta-value">{formatK(remaining)}</span>
        </div>
        <div className="budget-meta-item">
          <span className="budget-meta-label">Total</span>
          <span className="budget-meta-value">{formatK(total)}</span>
        </div>
      </div>

      <div className="budget-bar-track">
        <div
          className="budget-bar-fill"
          style={{ width: `${pct}%`, background: fillColor }}
        />
      </div>
    </div>
  )
}
