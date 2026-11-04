// client/src/views/QueryReview.jsx
// Mode 2: query-scoped review. Given a processed document's documentId,
// submit a query to /query and review only the retrieved claims. The
// server returns them already sorted risk-tier-first (Unformalized, High,
// Medium, Low; BM25-tiebroken) -- this view renders them EXACTLY in the
// order received and never re-sorts client-side.
import React, { useState, useEffect } from 'react';
import ClaimCard from '../ClaimCard.jsx';
import { fetchJson, postJson } from '../api.js';
import { TIER_LEGEND, panelStyle, sectionTitleStyle, errorBoxStyle } from '../tiers.js';

export default function QueryReview({ documentId: latestDocumentId, documentName }) {
  const [docId, setDocId] = useState(latestDocumentId || '');
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(10);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [response, setResponse] = useState(null);
  const [decisions, setDecisions] = useState({});

  // When a new document finishes formalizing in the Batch view, adopt its
  // documentId here (manual entry still possible for older documents).
  useEffect(() => {
    if (latestDocumentId) setDocId(latestDocumentId);
  }, [latestDocumentId]);

  const refreshDecisions = async () => {
    try {
      const reviewsData = await fetchJson('/reviews');
      const loaded = {};
      for (const [id, rec] of Object.entries(reviewsData)) loaded[id] = rec.decision;
      setDecisions(loaded);
    } catch {
      setDecisions({});
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setResponse(null);
    if (!docId.trim()) {
      setError('A document ID is required. Formalize a document in the Batch review view first, or paste an existing document ID.');
      return;
    }
    if (!query.trim()) {
      setError('Enter a query.');
      return;
    }
    setIsLoading(true);
    try {
      const data = await postJson('/query', {
        documentId: docId.trim(),
        query: query.trim(),
        topK: Number(topK) || 10,
      });
      setResponse(data);
      await refreshDecisions();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecide = async (claimId, decision) => {
    setDecisions((prev) => ({ ...prev, [claimId]: decision }));
    try {
      await postJson('/review', { claimId, decision });
    } catch (err) {
      setError(`Failed to record decision: ${err.message}`);
    }
  };

  return (
    <div>
      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>Query-scoped review</h2>
        <p style={{ margin: '0 0 12px', color: '#444', fontSize: 14 }}>
          Retrieve only the claims relevant to a question, ordered by the server
          risk-tier-first (Unformalized → High → Medium → Low, ties broken by
          relevance) so the riskiest evidence is reviewed before it is trusted.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
          {TIER_LEGEND.map(({ tier, color, desc }) => (
            <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block' }} />
              <span><strong>{tier}</strong> — {desc}</span>
            </div>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
            Document ID
          </label>
          <input
            type="text"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            placeholder="Formalize a document in Batch review, or paste a document ID"
            style={inputStyle}
          />
          {latestDocumentId && docId === latestDocumentId && (
            <p style={{ margin: '4px 0 0', fontSize: 12, color: '#198754' }}>
              Using the document formalized this session{documentName ? ` (${documentName})` : ''}.
            </p>
          )}

          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, margin: '12px 0 4px' }}>
            Query
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What does the author claim about causation?"
            style={inputStyle}
          />

          <label style={{ display: 'block', fontSize: 14, fontWeight: 600, margin: '12px 0 4px' }}>
            Max results (topK)
          </label>
          <input
            type="number"
            min={1}
            max={100}
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
            style={{ ...inputStyle, width: 100 }}
          />

          <div style={{ marginTop: 14 }}>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                padding: '10px 24px', fontSize: 15, fontWeight: 600, borderRadius: 6,
                border: 'none', background: isLoading ? '#9aa5b1' : '#0d6efd', color: '#fff',
                cursor: isLoading ? 'default' : 'pointer',
              }}
            >
              {isLoading ? 'Retrieving…' : 'Retrieve claims'}
            </button>
          </div>
        </form>
      </section>

      {error && <div style={errorBoxStyle}>{error}</div>}

      {response && (
        <section style={panelStyle}>
          <h2 style={sectionTitleStyle}>Retrieved claims</h2>
          <p style={{ margin: '0 0 12px', color: '#444', fontSize: 14 }}>
            {response.results.length === 0
              ? 'No claims matched this query (no query-term overlap with any claim).'
              : `${response.results.length} claim${response.results.length === 1 ? '' : 's'} retrieved for `}
            {response.results.length > 0 && <em>“{response.query}”</em>}
            {response.results.length > 0 && ', shown in the server’s risk-tier-first order.'}
          </p>
          {response.results.map((claim) => (
            <ClaimCard
              key={claim.id}
              claim={claim}
              decision={decisions[claim.id]}
              onDecide={handleDecide}
            />
          ))}
        </section>
      )}
    </div>
  );
}

const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  fontSize: 14,
  border: '1px solid #ccc',
  borderRadius: 6,
  fontFamily: 'inherit',
};
