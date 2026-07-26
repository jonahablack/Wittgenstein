// client/src/ClaimCard.jsx
import React from 'react';

const TIER_COLORS = {
  // Distinct gray, not reused from High/Medium/Low -- this codebase's own
  // color language uses green/orange/red to mean "risk level of a claim
  // that WAS formalized." Falling back to Low's green (as this did before
  // "Unformalized" had its own entry) told a reviewer "no concern" about a
  // claim that in fact has no formal representation at all -- the opposite
  // of what that color is supposed to signal everywhere else in this UI.
  Unformalized: { bg: '#e2e3e5', fg: '#41464b', border: '#c4c8cb' },
  High: { bg: '#f8d7da', fg: '#842029', border: '#f1aeb5' },
  Medium: { bg: '#fff3cd', fg: '#664d03', border: '#ffe69c' },
  Low: { bg: '#d1e7dd', fg: '#0f5132', border: '#a3cfbb' },
};

const DECISION_STYLES = {
  approved: { active: '#28a745', label: 'Approved' },
  flagged: { active: '#fd7e14', label: 'Flagged' },
  rejected: { active: '#dc3545', label: 'Rejected' },
};

export default function ClaimCard({ claim, decision, onDecide }) {
  const tierColor = TIER_COLORS[claim.risk_tier] || TIER_COLORS.Low;

  return (
    <div style={{
      marginBottom: 15, padding: 15, background: '#fff', borderRadius: 6,
      border: `1px solid ${tierColor.border}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <span style={{
          display: 'inline-block', padding: '2px 10px', borderRadius: 12,
          background: tierColor.bg, color: tierColor.fg, fontSize: 12, fontWeight: 'bold',
        }}>
          {claim.risk_tier} risk
        </span>
        {decision && (
          <span style={{ fontSize: 12, color: DECISION_STYLES[decision]?.active, fontWeight: 'bold' }}>
            {DECISION_STYLES[decision]?.label}
          </span>
        )}
      </div>

      <div style={{ marginBottom: 6 }}><strong>Claim:</strong> {claim.english}</div>
      {claim.formal_logic != null || claim.formal_english != null ? (
        <>
          <div style={{ marginBottom: 4, color: '#444' }}>
            <strong>Logic:</strong>{' '}
            {claim.formal_logic ?? <em style={{ color: '#888' }}>not available -- formalization failed for this claim</em>}
          </div>
          <div style={{ marginBottom: 8, color: '#444' }}>
            <strong>English formalization:</strong>{' '}
            {claim.formal_english ?? <em style={{ color: '#888' }}>not available -- formalization failed for this claim</em>}
          </div>
        </>
      ) : (
        <div style={{ marginBottom: 8, color: '#444' }}>
          <strong>Formal:</strong>{' '}
          {claim.formal
            ? claim.formal
            : <em style={{ color: '#888' }}>not available -- formalization failed for this claim</em>}
        </div>
      )}

      {claim.risk_flags?.length > 0 && (
        <div style={{ margin: '0 0 10px' }}>
          <div style={{ fontSize: 11, fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: 0.4, color: '#888', marginBottom: 4 }}>
            Potential formalization risk — worth a human check, not a confirmed error
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#555' }}>
            {claim.risk_flags.map((f, i) => (
              <li key={i}><strong>{f.type.replace(/_/g, ' ')}:</strong> {f.reason}</li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        {Object.entries(DECISION_STYLES).map(([key, { active, label }]) => (
          <button
            key={key}
            onClick={() => onDecide(claim.id, key)}
            style={{
              padding: '4px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
              border: `1px solid ${active}`,
              background: decision === key ? active : '#fff',
              color: decision === key ? '#fff' : active,
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}