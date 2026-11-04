// client/src/ClaimCard.jsx
import React from 'react';
import { claimTierStyle } from './tiers.js';

const DECISION_STYLES = {
  approved: { active: '#28a745', label: 'Approved' },
  flagged: { active: '#fd7e14', label: 'Flagged' },
  rejected: { active: '#dc3545', label: 'Rejected' },
};

const NOT_AVAILABLE = (
  <em style={{ color: '#888' }}>not available -- formalization failed for this claim</em>
);

// The claim itself: tier badge (only if the server sent a tier), english
// text, formal representation(s) with an explicit "not available" message
// for anything null/missing, risk flags (only if the server sent them),
// and the source segment reference. Shared by batch review, query-scoped
// review, and the study harness -- the study harness relies on this
// rendering NOTHING risk-related when those fields are absent.
export function ClaimBody({ claim }) {
  const tierColor = claimTierStyle(claim);
  const hasSplitFields = claim.formal_logic !== undefined || claim.formal_english !== undefined;

  return (
    <>
      {claim.risk_tier != null && (
        <div style={{ marginBottom: 8 }}>
          <span style={{
            display: 'inline-block', padding: '2px 10px', borderRadius: 12,
            background: tierColor.bg, color: tierColor.fg, fontSize: 12, fontWeight: 'bold',
          }}>
            {claim.risk_tier} risk
          </span>
        </div>
      )}

      <div style={{ marginBottom: 6 }}><strong>Claim:</strong> {claim.english}</div>

      {hasSplitFields ? (
        <>
          <div style={{ marginBottom: 4, color: '#444' }}>
            <strong>Logic:</strong>{' '}
            {claim.formal_logic ?? NOT_AVAILABLE}
          </div>
          <div style={{ marginBottom: 8, color: '#444' }}>
            <strong>English formalization:</strong>{' '}
            {claim.formal_english ?? NOT_AVAILABLE}
          </div>
        </>
      ) : (
        <div style={{ marginBottom: 8, color: '#444' }}>
          <strong>Formal:</strong>{' '}
          {claim.formal ? claim.formal : NOT_AVAILABLE}
        </div>
      )}

      {(claim.segment_index != null || claim.claim_index != null) && (
        <div style={{ marginBottom: 8, fontSize: 12, color: '#777' }}>
          Source:
          {claim.segment_index != null ? ` segment ${claim.segment_index}` : ''}
          {claim.segment_index != null && claim.claim_index != null ? ',' : ''}
          {claim.claim_index != null ? ` claim ${claim.claim_index}` : ''}
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
    </>
  );
}

export default function ClaimCard({ claim, decision, onDecide }) {
  const tierColor = claimTierStyle(claim);

  return (
    <div style={{
      marginBottom: 15, padding: 15, background: '#fff', borderRadius: 6,
      border: `1px solid ${tierColor.border}`,
    }}>
      {decision && (
        <div style={{ float: 'right', fontSize: 12, color: DECISION_STYLES[decision]?.active, fontWeight: 'bold' }}>
          {DECISION_STYLES[decision]?.label}
        </div>
      )}

      <ClaimBody claim={claim} />

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
