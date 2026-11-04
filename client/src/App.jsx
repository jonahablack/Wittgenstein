// client/src/App.jsx
// Top-level shell. Three clearly separated modes, each its own view module:
//   1. Batch review        (views/BatchReview.jsx)  -- whole-document review
//   2. Query review        (views/QueryReview.jsx)  -- query-scoped retrieval
//   3. Study harness       (views/StudyHarness.jsx) -- participant flow, with
//      a researcher-only Admin toggle (views/StudyAdmin.jsx)
//
// Inactive views stay mounted but hidden so switching tabs never discards
// in-progress work (an upload, typed query, or half-finished study item).
import React, { useState } from 'react';
import AboutModal from './AboutModal.jsx';
import BatchReview from './views/BatchReview.jsx';
import QueryReview from './views/QueryReview.jsx';
import StudyHarness from './views/StudyHarness.jsx';
import StudyAdmin from './views/StudyAdmin.jsx';

const MODES = [
  { id: 'batch', label: 'Batch review', desc: 'Upload a document and review every extracted claim, sorted by risk tier.' },
  { id: 'query', label: 'Query review', desc: 'Ask a question of a processed document and review only the retrieved claims, riskiest first.' },
  { id: 'study', label: 'Study harness', desc: 'Participant-facing review session for the human study.' },
];

export default function App() {
  const [mode, setMode] = useState('batch');
  const [showAbout, setShowAbout] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  // Set when a formalization completes in Batch review; lets Query review
  // pre-fill the documentId without re-processing.
  const [latestDocument, setLatestDocument] = useState(null);

  const activeMode = MODES.find((m) => m.id === mode);

  return (
    <div style={{ maxWidth: 880, margin: '0 auto', padding: '40px 24px 80px', fontFamily: 'system-ui, Arial, sans-serif', color: '#1a1a1a' }}>
      <header style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
          <h1 style={{ margin: '0 0 8px', fontSize: 32 }}>Wittgenstein</h1>
          <button
            onClick={() => setShowAbout(true)}
            style={{
              background: 'none', border: '1px solid #999', borderRadius: 6, cursor: 'pointer',
              padding: '4px 12px', fontSize: 13, color: '#333', whiteSpace: 'nowrap',
            }}
          >
            About
          </button>
        </div>
        <p style={{ margin: 0, fontSize: 16, color: '#444', lineHeight: 1.5 }}>
          Upload a PDF or EPUB. Wittgenstein extracts its central content and flags text likely to be misinterpreted, with a plain-language reason for each flag.
        </p>
      </header>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}

      <nav style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            style={{
              padding: '8px 18px', fontSize: 14, fontWeight: 600, borderRadius: '8px 8px 0 0',
              cursor: 'pointer',
              border: '1px solid #ccc',
              borderBottom: mode === m.id ? '2px solid #0d6efd' : '1px solid #ccc',
              background: mode === m.id ? '#fff' : '#eceef1',
              color: mode === m.id ? '#0d6efd' : '#555',
            }}
          >
            {m.label}
          </button>
        ))}
        {mode === 'study' && (
          <button
            onClick={() => setShowAdmin((v) => !v)}
            style={{
              marginLeft: 'auto', padding: '8px 14px', fontSize: 13, fontWeight: 600,
              borderRadius: 6, cursor: 'pointer',
              border: '1px solid #055160',
              background: showAdmin ? '#055160' : '#fff',
              color: showAdmin ? '#fff' : '#055160',
            }}
          >
            {showAdmin ? 'Back to participant view' : 'Admin'}
          </button>
        )}
      </nav>
      <p style={{ margin: '0 0 20px', fontSize: 13, color: '#666' }}>{activeMode?.desc}</p>

      <div style={{ display: mode === 'batch' ? 'block' : 'none' }}>
        <BatchReview
          onDocumentReady={(documentId, fileName) => setLatestDocument({ documentId, fileName })}
        />
      </div>

      <div style={{ display: mode === 'query' ? 'block' : 'none' }}>
        <QueryReview
          documentId={latestDocument?.documentId}
          documentName={latestDocument?.fileName}
        />
      </div>

      <div style={{ display: mode === 'study' ? 'block' : 'none' }}>
        {showAdmin ? <StudyAdmin /> : <StudyHarness />}
      </div>
    </div>
  );
}
