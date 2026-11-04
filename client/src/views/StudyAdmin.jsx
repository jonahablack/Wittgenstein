// client/src/views/StudyAdmin.jsx
// Researcher-only admin panel for the study harness. This is the ONLY
// place in the client where a session's condition (blind vs. triaged) is
// ever selected or displayed -- the participant flow (StudyHarness.jsx)
// must never see or send it.
import React, { useState, useEffect, useCallback } from 'react';
import { fetchJson, postJson } from '../api.js';
import { panelStyle, sectionTitleStyle, errorBoxStyle } from '../tiers.js';

const COHORTS = ['clinical', 'legal'];
const CONDITIONS = ['blind', 'triaged'];

export default function StudyAdmin() {
  const [participantId, setParticipantId] = useState('');
  const [cohort, setCohort] = useState('clinical');
  const [condition, setCondition] = useState('blind');
  const [documentId, setDocumentId] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [error, setError] = useState(null);

  const [sessionIds, setSessionIds] = useState([]);
  const [listError, setListError] = useState(null);
  const [exportingId, setExportingId] = useState(null);

  const refreshSessions = useCallback(async () => {
    setListError(null);
    try {
      const data = await fetchJson('/study/admin/sessions');
      setSessionIds(data.session_ids || []);
    } catch (err) {
      setListError(err.message);
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setError(null);
    setCreated(null);
    setIsCreating(true);
    try {
      const body = { participant_id: participantId.trim(), cohort, condition };
      if (documentId.trim()) body.document_id = documentId.trim();
      const data = await postJson('/study/admin/sessions', body);
      setCreated(data);
      await refreshSessions();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleExport = async (sid) => {
    setListError(null);
    setExportingId(sid);
    try {
      const record = await fetchJson(`/study/sessions/${encodeURIComponent(sid)}/export`);
      const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `study_export_${sid}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setListError(`Export failed for ${sid}: ${err.message}`);
    } finally {
      setExportingId(null);
    }
  };

  return (
    <div>
      <div style={{
        margin: '0 0 16px', padding: '10px 14px', background: '#cff4fc',
        border: '1px solid #9eeaf9', borderRadius: 6, color: '#055160', fontSize: 14,
      }}>
        <strong>Admin panel — researchers only.</strong> Condition assignment
        happens here and only here. Never show this screen to a participant.
      </div>

      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>Create a session</h2>
        <form onSubmit={handleCreate}>
          <label style={labelStyle}>Participant ID</label>
          <input
            type="text"
            value={participantId}
            onChange={(e) => setParticipantId(e.target.value)}
            placeholder="e.g. P-014"
            style={inputStyle}
          />

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
            <div>
              <label style={labelStyle}>Cohort</label>
              <select value={cohort} onChange={(e) => setCohort(e.target.value)} style={selectStyle}>
                {COHORTS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Condition</label>
              <select value={condition} onChange={(e) => setCondition(e.target.value)} style={selectStyle}>
                {CONDITIONS.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          <label style={{ ...labelStyle, marginTop: 12 }}>Document ID (optional — defaults to the study config's document)</label>
          <input
            type="text"
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            placeholder="Leave blank to use the configured study document"
            style={inputStyle}
          />

          <div style={{ marginTop: 14 }}>
            <button
              type="submit"
              disabled={isCreating}
              style={{
                padding: '10px 24px', fontSize: 15, fontWeight: 600, borderRadius: 6,
                border: 'none', background: isCreating ? '#9aa5b1' : '#0d6efd', color: '#fff',
                cursor: isCreating ? 'default' : 'pointer',
              }}
            >
              {isCreating ? 'Creating…' : 'Create session'}
            </button>
          </div>
        </form>

        {error && <div style={errorBoxStyle}>{error}</div>}

        {created && (
          <div style={{
            marginTop: 14, padding: 12, background: '#d1e7dd', color: '#0f5132',
            border: '1px solid #a3cfbb', borderRadius: 6, fontSize: 14,
          }}>
            Session created for <strong>{created.participant_id}</strong>
            {' '}({created.cohort}, {created.condition}) with {created.item_count} items.
            <div style={{ marginTop: 6 }}>
              Give the participant this session ID:
              {' '}<code style={{ userSelect: 'all' }}>{created.session_id}</code>
            </div>
          </div>
        )}
      </section>

      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>Sessions on disk</h2>
        <button
          onClick={refreshSessions}
          style={{
            padding: '4px 12px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
            border: '1px solid #999', background: '#fff', color: '#333', marginBottom: 10,
          }}
        >
          Refresh list
        </button>
        {listError && <div style={errorBoxStyle}>{listError}</div>}
        {sessionIds.length === 0 && !listError && (
          <p style={{ fontStyle: 'italic', color: '#666', margin: 0 }}>No sessions yet.</p>
        )}
        {sessionIds.map((sid) => (
          <div
            key={sid}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              gap: 12, padding: '8px 0', borderBottom: '1px solid #eee', fontSize: 14,
            }}
          >
            <code style={{ wordBreak: 'break-all' }}>{sid}</code>
            <button
              onClick={() => handleExport(sid)}
              disabled={exportingId === sid}
              style={{
                padding: '4px 14px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                border: '1px solid #198754', background: '#fff', color: '#198754',
                whiteSpace: 'nowrap',
              }}
            >
              {exportingId === sid ? 'Exporting…' : 'Download export JSON'}
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}

const labelStyle = {
  display: 'block',
  fontSize: 14,
  fontWeight: 600,
  marginBottom: 4,
};

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  fontSize: 14,
  border: '1px solid #ccc',
  borderRadius: 6,
  fontFamily: 'inherit',
};

const selectStyle = {
  padding: '8px 10px',
  fontSize: 14,
  border: '1px solid #ccc',
  borderRadius: 6,
  fontFamily: 'inherit',
  minWidth: 140,
};
