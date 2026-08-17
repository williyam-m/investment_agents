function recLabel(rec) {
  return (rec || 'N/A').replace(/_/g, ' ').toUpperCase()
}

function convictionPct(val) {
  if (val == null) return 0
  return val > 1 ? Math.min(100, val) : Math.min(100, val * 100)
}

function formatTokens(n) {
  if (!n && n !== 0) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

const AGENT_LABELS = {
  value_investor:   '📊 Value Investor',
  momentum_trader:  '📈 Momentum Trader',
  risk_analyst:     '⚠️ Risk Analyst',
  macro_economist:  '🌍 Macro Economist',
  contrarian:       '🔄 Contrarian',
  tiebreaker:       '⚖️ Tiebreaker',
  synthesis:        '📋 Synthesis',
}

export default function CommitteeMemo({ memo }) {
  if (!memo) return null

  const {
    final_recommendation,
    conviction,
    executive_summary,
    bull_case,
    bear_case,
    key_risks = [],
    catalysts_to_watch = [],
    vote_breakdown = {},
    dissenting_views = [],
    debate_was_contentious,
    committee_divided,
    total_tokens_used,
    model_used,
    synthesis_quality,
  } = memo

  const rec    = (final_recommendation || 'hold').toLowerCase().replace(/ /g, '_')
  const convPct = convictionPct(conviction)

  // Normalize vote_breakdown: {rec_name: count} or {agent: rec}
  const voteEntries = Object.entries(vote_breakdown).map(([key, val]) => {
    if (typeof val === 'number') return { label: key, count: val }
    if (typeof val === 'object' && val !== null) {
      return { label: key, rec: val.recommendation || val.rec || 'hold', count: 1 }
    }
    return { label: key, rec: val, count: 1 }
  })

  return (
    <div className="memo-wrapper">

      {/* ── Header ── */}
      <div className="memo-header">
        <div className="memo-header-top">
          <span className="memo-label">Committee Memo</span>
          {synthesis_quality && (
            <span className="memo-quality-badge">
              {synthesis_quality === 'full' ? '✓ Full Analysis' : '⚠ Degraded'}
            </span>
          )}
        </div>

        {/* Recommendation + Conviction */}
        <div className="memo-rec-row">
          <span className={`memo-rec-badge rec-${rec}`}>
            {recLabel(final_recommendation)}
          </span>

          <div className="memo-conviction">
            <span className="memo-conviction-label">Conviction</span>
            <div className="memo-conviction-bar-track">
              <div
                className={`memo-conviction-bar-fill ${rec}`}
                style={{ width: `${convPct}%` }}
              />
            </div>
            <span className="memo-conviction-pct">{convPct.toFixed(0)}%</span>
          </div>
        </div>

        {/* Vote chips (if numeric breakdown) */}
        {voteEntries.length > 0 && (
          <div className="memo-votes" style={{ marginTop: 10 }}>
            {voteEntries.map(({ label, count, rec: vRec }, i) => (
              <span key={i} className="memo-vote-chip">
                {vRec
                  ? `${recLabel(vRec)} — ${AGENT_LABELS[label] || label.replace(/_/g, ' ')}`
                  : `${recLabel(label)} × ${count}`
                }
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Body ── */}
      <div className="memo-body">

        {/* Executive Summary */}
        {executive_summary && (
          <div>
            <div className="memo-section-title">Executive Summary</div>
            <div className="memo-executive-summary">{executive_summary}</div>
          </div>
        )}

        {/* Bull / Bear */}
        {(bull_case || bear_case) && (
          <div>
            <div className="memo-section-title">Investment Cases</div>
            <div className="memo-cases">
              {bull_case && (
                <div className="memo-case bull">
                  <div className="memo-case-title">↑ Bull Case</div>
                  <p className="memo-case-text">{bull_case}</p>
                </div>
              )}
              {bear_case && (
                <div className="memo-case bear">
                  <div className="memo-case-title">↓ Bear Case</div>
                  <p className="memo-case-text">{bear_case}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Key Risks */}
        {key_risks.length > 0 && (
          <div>
            <div className="memo-section-title">Key Risks</div>
            <div className="memo-list">
              {key_risks.map((risk, i) => (
                <div key={i} className="memo-list-item">
                  <span className="memo-list-dot" />
                  <span>{typeof risk === 'string' ? risk : risk.description || JSON.stringify(risk)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Catalysts */}
        {catalysts_to_watch.length > 0 && (
          <div>
            <div className="memo-section-title">Catalysts to Watch</div>
            <div className="memo-list">
              {catalysts_to_watch.map((cat, i) => (
                <div key={i} className="memo-list-item">
                  <span className="memo-list-dot" style={{ background: 'var(--blue)' }} />
                  <span>{typeof cat === 'string' ? cat : JSON.stringify(cat)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Debate Dynamics */}
        {(debate_was_contentious != null || committee_divided != null) && (
          <div>
            <div className="memo-section-title">Committee Dynamics</div>
            <div className="memo-dynamics">
              {debate_was_contentious != null && (
                <span className="dynamics-badge">
                  {debate_was_contentious ? '🔥 Contentious Debate' : '🤝 Consensus Debate'}
                </span>
              )}
              {committee_divided != null && (
                <span className="dynamics-badge">
                  {committee_divided ? '⚔️ Committee Divided' : '✅ Committee Aligned'}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Dissenting Views */}
        {dissenting_views.length > 0 && (
          <div>
            <div className="memo-section-title">Dissenting Views</div>
            <div className="memo-list" style={{ gap: 8 }}>
              {dissenting_views.map((dv, i) => {
                const dvRec = (dv.recommendation || 'hold').toLowerCase().replace(/ /g, '_')
                return (
                  <div key={i} className="dissent-card">
                    <div className="dissent-card-header">
                      <span className="dissent-agent">
                        {AGENT_LABELS[dv.agent_type] || dv.agent_type}
                      </span>
                      <span className={`dissent-rec rec-${dvRec}`}>
                        {recLabel(dv.recommendation)}
                      </span>
                    </div>
                    {dv.key_argument && (
                      <p className="dissent-arg">{dv.key_argument}</p>
                    )}
                    {dv.why_not_adopted && (
                      <p className="dissent-reason">Not adopted: {dv.why_not_adopted}</p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="memo-stats">
          {total_tokens_used != null && (
            <div className="memo-stat">
              <span className="memo-stat-label">Tokens Used</span>
              <span className="memo-stat-value">{formatTokens(total_tokens_used)}</span>
            </div>
          )}
          {model_used && (
            <div className="memo-stat">
              <span className="memo-stat-label">Model</span>
              <span className="memo-stat-value" style={{ fontSize: 11 }}>
                {model_used.replace('ollama/', '')}
              </span>
            </div>
          )}
          {conviction != null && (
            <div className="memo-stat">
              <span className="memo-stat-label">Conviction</span>
              <span className="memo-stat-value">{convPct.toFixed(0)}%</span>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
