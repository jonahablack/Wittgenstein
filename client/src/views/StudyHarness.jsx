// client/src/views/StudyHarness.jsx
// Mode 3: study-harness participant flow. The participant enters the
// session_id a researcher gave them and steps through items one at a time
// via GET /study/sessions/<sid>/items/next.
//
// Deliberate design constraints (do not "fix" these):
//  - Only /items/next is used, never /items or any /study/admin route: the
//    participant flow must not even receive the session's condition, so it
//    cannot leak it.
//  - No tier/flag styling is conditioned on anything the server didn't
//    send. In the blind condition the server strips risk fields; ClaimBody
//    renders a badge/flags ONLY when those fields are present in the
//    payload. The client adds nothing of its own.
import React, { useState } from 'react';
import { ClaimBody } from '../ClaimCard.jsx';
import { fetchJson, postJson } from '../api.js';
import { claimTierStyle, panelStyle, sectionTitleStyle, errorBoxStyle } from '../tiers.js';

const DECISION_OPTIONS = [
  { value: 'approved', label: 'Approved', color: '#28a745' },
  { value: 'flagged', label: 'Flagged', color: '#fd7e14' },
  { value: 'rejected', label: 'Rejected', color: '#dc3545' },
];

export default function StudyHarness() {
  const [sessionIdInput, setSessionIdInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [item, setItem] = useState(null);
  const [done, setDone] = useState(false);
  const [completedCount, setCompletedCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Per-item decision controls.
  const [decision, setDecision] = useState(null);
  const [confidence, setConfidence] = useState(null);
  const [weakSource, setWeakSource] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetControls = () => {
    setDecision(null);
    setConfidence(null);
    setWeakSource('');
  };

  const loadNext = async (sid) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchJson(`/study/sessions/${encodeURIComponent(sid)}/items/next`);
      if (data.done) {
        setDone(true);
        setItem(null);
      } else {
        setItem(data.item);
        setDone(false);
      }
      resetControls();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStart = async (e) => {
    e.preventDefault();
    const sid = sessionIdInput.trim();
    if (!sid) {
      setError('Enter the session ID you were given.');
      return;
    }
    setSessionId(sid);
    setCompletedCount(0);
    setDone(false);
    setItem(null);
    await loadNext(sid);
  };

  const needsWeakSource = decision === 'flagged' && item?.item_type === 'query_verification';

  const handleSubmit = async () => {
    setError(null);
    if (!decision) {
      setError('Choose Approved, Flagged, or Rejected.');
      return;
    }
    if (!confidence) {
      setError('Select a confidence rating (1–5).');
      return;
    }
    if (needsWeakSource && weakSource === '') {
      setError('You flagged this answer — identify which source claim is the weak one.');
      return;
    }
    setIsSubmitting(true);
    try {
      const body = {
        item_id: item.item_id,
        decision,
        confidence,
      };
      if (needsWeakSource) body.identified_weak_source = Number(weakSource);
      await postJson(`/study/sessions/${encodeURIComponent(sessionId)}/decisions`, body);
      setCompletedCount((n) => n + 1);
      await loadNext(sessionId);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>Study session</h2>
        {!sessionId && (
          <p style={{ margin: '0 0 12px', color: '#444', fontSize: 14 }}>
            Enter the session ID provided by the research team. You will review a
            series of items one at a time; for each, choose a decision and rate
            your confidence.
          </p>
        )}
        <form onSubmit={handleStart} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input
            type="text"
            value={sessionIdInput}
            onChange={(e) => setSessionIdInput(e.target.value)}
            placeholder="Session ID"
            style={{
              flex: '1 1 320px', padding: '8px 10px', fontSize: 14,
              border: '1px solid #ccc', borderRadius: 6, fontFamily: 'inherit',
            }}
          />
          <button
            type="submit"
            disabled={isLoading}
            style={{
              padding: '8px 20px', fontSize: 14, fontWeight: 600, borderRadius: 6,
              border: 'none', background: '#0d6efd', color: '#fff', cursor: 'pointer',
            }}
          >
            {sessionId ? 'Switch session' : 'Start'}
          </button>
        </form>
        {sessionId && (
          <p style={{ margin: '10px 0 0', fontSize: 13, color: '#666' }}>
            Session <code>{sessionId}</code> — {completedCount} decision{completedCount === 1 ? '' : 's'} submitted this sitting.
          </p>
        )}
      </section>

      {error && <div style={errorBoxStyle}>{error}</div>}

      {isLoading && (
        <p style={{ color: '#666' }}>Loading next item…</p>
      )}

      {done && (
        <section style={panelStyle}>
          <h2 style={sectionTitleStyle}>Session complete</h2>
          <p style={{ margin: 0, color: '#444' }}>
            Every item in this session has a decision. Thank you — you can close
            this window.
          </p>
        </section>
      )}

      {item && !isLoading && (
        <section style={panelStyle}>
          {item.item_type === 'batch_claim' ? (
            <>
              <h2 style={sectionTitleStyle}>Review this claim</h2>
              <div style={claimBoxStyle(item)}>
                <ClaimBody claim={item} />
              </div>
            </>
          ) : (
            <>
              <h2 style={sectionTitleStyle}>Verify this answer</h2>
              <div style={{ marginBottom: 12, padding: 12, background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: 6 }}>
                <div style={{ marginBottom: 6 }}><strong>Question:</strong> {item.query}</div>
                <div><strong>Answer:</strong> {item.answer}</div>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#555', marginBottom: 8 }}>
                Sources the answer was drawn from:
              </div>
              {item.sources.map((src) => (
                <div key={src.claim_index} style={claimBoxStyle(src)}>
                  <ClaimBody claim={src} />
                </div>
              ))}
            </>
          )}

          <hr style={{ border: 'none', borderTop: '1px solid #e3e5e8', margin: '16px 0' }} />

          <div style={{ marginBottom: 12 }}>
            <span style={{ fontWeight: 600, fontSize: 14, display: 'block', marginBottom: 6 }}>Your decision</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {DECISION_OPTIONS.map(({ value, label, color }) => (
                <button
                  key={value}
                  onClick={() => setDecision(value)}
                  style={{
                    padding: '6px 16px', fontSize: 14, borderRadius: 4, cursor: 'pointer',
                    border: `1px solid ${color}`,
                    background: decision === value ? color : '#fff',
                    color: decision === value ? '#fff' : color,
                    fontWeight: 600,
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {needsWeakSource && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontWeight: 600, fontSize: 14, display: 'block', marginBottom: 6 }}>
                Which source claim is the weak one?
              </label>
              <select
                value={weakSource}
                onChange={(e) => setWeakSource(e.target.value)}
                style={{ padding: '6px 10px', fontSize: 14, borderRadius: 6, border: '1px solid #ccc', fontFamily: 'inherit' }}
              >
                <option value="">— select a source claim —</option>
                {item.sources.map((src) => (
                  <option key={src.claim_index} value={src.claim_index}>
                    Claim {src.claim_index}: {(src.english || '').slice(0, 80)}{(src.english || '').length > 80 ? '…' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <span style={{ fontWeight: 600, fontSize: 14, display: 'block', marginBottom: 6 }}>
              Confidence (1 = not at all confident, 5 = very confident)
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setConfidence(n)}
                  style={{
                    width: 38, height: 38, fontSize: 15, borderRadius: 6, cursor: 'pointer',
                    border: '1px solid #999',
                    background: confidence === n ? '#333' : '#fff',
                    color: confidence === n ? '#fff' : '#333',
                    fontWeight: 600,
                  }}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={isSubmitting}
            style={{
              padding: '10px 28px', fontSize: 15, fontWeight: 600, borderRadius: 6,
              border: 'none', background: isSubmitting ? '#9aa5b1' : '#198754', color: '#fff',
              cursor: isSubmitting ? 'default' : 'pointer',
            }}
          >
            {isSubmitting ? 'Submitting…' : 'Submit decision'}
          </button>
        </section>
      )}
    </div>
  );
}

// Border color comes from claimTierStyle, which resolves to a neutral gray
// whenever the payload carries no risk_tier (blind condition) -- the border
// only ever encodes information the server actually sent.
function claimBoxStyle(claim) {
  return {
    marginBottom: 12,
    padding: 14,
    background: '#fff',
    borderRadius: 6,
    border: `1px solid ${claimTierStyle(claim).border}`,
  };
}
