// client/src/tiers.js
// Single source of truth for risk-tier ordering, filtering, colors, and
// legend copy. "Unformalized" is a first-class tier in EVERY structure
// here -- sort order, filter list, color map, legend -- so no view can
// accidentally drop it by consulting only one of them.

// "Unformalized" sorts first (priority 0, ahead of even High) rather than
// falling through to a default -- a claim with no formal representation at
// all is a more complete failure than any risk-flagged but
// successfully-formalized claim, and deserves top billing.
export const TIER_ORDER = { Unformalized: 0, High: 1, Medium: 2, Low: 3 };

export const TIER_FILTERS = ['All', 'Unformalized', 'High', 'Medium', 'Low'];

export const TIER_LEGEND = [
  { tier: 'Unformalized', color: '#6c757d', desc: 'no formal representation was produced for this claim -- review the source directly' },
  { tier: 'High', color: '#dc3545', desc: '2+ weighted flags (e.g. modal mismatch or ambiguous negation)' },
  { tier: 'Medium', color: '#fd7e14', desc: 'one moderate flag, or several minor ones' },
  { tier: 'Low', color: '#198754', desc: 'no risk flags detected' },
];

export const TIER_COLORS = {
  // Distinct gray, not reused from High/Medium/Low -- this codebase's own
  // color language uses green/orange/red to mean "risk level of a claim
  // that WAS formalized." Reusing Low's green would tell a reviewer "no
  // concern" about a claim that has no formal representation at all.
  Unformalized: { bg: '#e2e3e5', fg: '#41464b', border: '#c4c8cb' },
  High: { bg: '#f8d7da', fg: '#842029', border: '#f1aeb5' },
  Medium: { bg: '#fff3cd', fg: '#664d03', border: '#ffe69c' },
  Low: { bg: '#d1e7dd', fg: '#0f5132', border: '#a3cfbb' },
};

// Neutral style for a claim with NO tier information at all (e.g. the study
// harness blind condition, where the server strips risk fields). This must
// never look like any real tier -- especially not Low's "all clear" green.
export const NO_TIER_STYLE = { bg: '#f1f3f5', fg: '#495057', border: '#dee2e6' };

// A tier the color map doesn't know (or no tier at all, as in the study
// harness blind condition) gets the neutral style -- NEVER Low's green.
export function claimTierStyle(claim) {
  return TIER_COLORS[claim.risk_tier] || NO_TIER_STYLE;
}

// Shared layout styles (kept identical to the original App.jsx look).
export const panelStyle = {
  background: '#fff',
  border: '1px solid #e3e5e8',
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
};

export const sectionTitleStyle = {
  margin: '0 0 12px',
  fontSize: 17,
};

export const btnStyle = {
  padding: '10px 18px',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: 15,
  fontWeight: 600,
  textAlign: 'left',
};

export const errorBoxStyle = {
  color: '#842029',
  margin: '16px 0',
  padding: 12,
  background: '#f8d7da',
  border: '1px solid #f1aeb5',
  borderRadius: 6,
};
