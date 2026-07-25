// client/src/App.jsx
import React, { useState } from 'react';
import FileUpload from './FileUpload.jsx';
import ClaimCard from './ClaimCard.jsx';
import AboutModal from './AboutModal.jsx';

const TIER_ORDER = { High: 0, Medium: 1, Low: 2 };
const TIER_FILTERS = ['All', 'High', 'Medium', 'Low'];
const TIER_LEGEND = [
  { tier: 'High', color: '#dc3545', desc: '2+ weighted flags (e.g. modal mismatch or ambiguous negation)' },
  { tier: 'Medium', color: '#fd7e14', desc: 'one moderate flag, or several minor ones' },
  { tier: 'Low', color: '#198754', desc: 'no risk flags detected' },
];
const FORMALIZE_OPTIONS = [
  { type: 'logic', label: 'Formal Logic', desc: 'symbolic logic only', color: '#0d6efd' },
  { type: 'english', label: 'English Formalization', desc: 'structured English only', color: '#198754' },
  { type: 'both', label: 'Both', desc: 'logic + English side by side', color: '#6f42c1' },
];

export default function App() {
  const [fileId, setFileId] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [formalizationData, setFormalizationData] = useState(null);
  const [resultsByType, setResultsByType] = useState({});
  const [formalizeType, setFormalizeType] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [tierFilter, setTierFilter] = useState('All');
  const [decisions, setDecisions] = useState({});
  const [showAbout, setShowAbout] = useState(false);

  const refreshDecisions = async () => {
    try {
      const reviewsRes = await fetch('/reviews');
      const reviewsData = await reviewsRes.json();
      const loaded = {};
      for (const [id, rec] of Object.entries(reviewsData)) loaded[id] = rec.decision;
      setDecisions(loaded);
    } catch {
      setDecisions({});
    }
  };

  const onFileUpload = async (file) => {
    setError(null);
    setFormalizationData(null);
    setResultsByType({});
    setFormalizeType(null);
    setFileId(null);
    setUploadedFileName(null);
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.fileId) {
        setFileId(data.fileId);
        setUploadedFileName(file.name);
      } else {
        setError(data.error || 'Upload failed.');
      }
    } catch {
      setError('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleFormalize = async (type) => {
    if (!fileId) return;
    setError(null);
    setFormalizeType(type);

    // Already generated this formalization for the current file -- reuse it
    // instead of re-running claim extraction + LLM calls from scratch.
    const cached = resultsByType[type];
    if (cached) {
      setFormalizationData(cached);
      setTierFilter('All');
      await refreshDecisions();
      return;
    }

    setIsProcessing(true);
    try {
      const res = await fetch('/formalize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fileId, formatType: type, useParallel: true, maxWorkers: 5 }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResultsByType((prev) => ({ ...prev, [type]: data }));
        setFormalizationData(data);
        setTierFilter('All');
        await refreshDecisions();
      }
    } catch {
      setError('Formalization failed. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDecide = async (claimId, decision) => {
    setDecisions((prev) => ({ ...prev, [claimId]: decision }));
    try {
      await fetch('/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claimId, decision }),
      });
    } catch {
      // best-effort logging; UI state already reflects the choice
    }
  };

  const visibleClaims = (formalizationData?.axioms || [])
    .filter((a) => tierFilter === 'All' || a.risk_tier === tierFilter)
    .sort((a, b) => (TIER_ORDER[a.risk_tier] ?? 3) - (TIER_ORDER[b.risk_tier] ?? 3));

  return (
    <div style={{ maxWidth: 880, margin: '0 auto', padding: '40px 24px 80px', fontFamily: 'system-ui, Arial, sans-serif', color: '#1a1a1a' }}>
      <header style={{ marginBottom: 28 }}>
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

      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>Risk-triage classifier</h2>
        <p style={{ margin: '0 0 12px', color: '#444', fontSize: 14 }}>
          Every formalized claim is screened by a rule-based classifier and sorted into a tier, so human reviewers know where to focus their attention. Flags are drawn from documented failure modes in the literature, and tiers are set by a weighted count of the flags below.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {TIER_LEGEND.map(({ tier, color, desc }) => (
            <div key={tier} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block' }} />
              <span><strong>{tier}</strong> — {desc}</span>
            </div>
          ))}
        </div>
      </section>

      <section style={panelStyle}>
        <h2 style={sectionTitleStyle}>1. Upload a document</h2>
        <FileUpload onFileUpload={onFileUpload} />
        {isUploading && (
          <p style={{ margin: '10px 0 0', fontSize: 14, color: '#666' }}>Uploading…</p>
        )}
        {uploadedFileName && !isUploading && (
          <div style={{
            marginTop: 10, padding: '8px 12px', background: '#d1e7dd', color: '#0f5132',
            border: '1px solid #a3cfbb', borderRadius: 6, fontSize: 14,
          }}>
            ✅ Uploaded <strong>{uploadedFileName}</strong> — choose a formalization below.
          </div>
        )}
      </section>

      {error && (
        <div style={{ color: '#842029', margin: '16px 0', padding: 12, background: '#f8d7da', border: '1px solid #f1aeb5', borderRadius: 6 }}>
          {error}
        </div>
      )}

      {formalizationData?.warning && (
        <div style={{ color: '#664d03', margin: '16px 0', padding: 12, background: '#fff3cd', border: '1px solid #ffe69c', borderRadius: 6 }}>
          ⚠️ {formalizationData.warning}
        </div>
      )}

      {fileId && !isProcessing && (
        <section style={panelStyle}>
          <h2 style={sectionTitleStyle}>2. Choose formalization</h2>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {FORMALIZE_OPTIONS.map(({ type, label, desc, color }) => (
              <button
                key={type}
                onClick={() => handleFormalize(type)}
                style={{
                  ...btnStyle,
                  backgroundColor: color,
                  outline: formalizeType === type ? '2px solid #1a1a1a' : 'none',
                  outlineOffset: 2,
                }}
              >
                {label}{resultsByType[type] ? ' ✓' : ''}
                <span style={{ display: 'block', fontSize: 11, fontWeight: 400, opacity: 0.85 }}>
                  {resultsByType[type] ? 'already generated — instant switch' : desc}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {isProcessing && (
        <div style={{ margin: '20px 0', padding: 20, background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: 6 }}>
          <p style={{ margin: 0 }}>Processing file, it may take a few minutes...</p>
          <p style={{ fontSize: 14, color: '#666', marginTop: 5, marginBottom: 0 }}>
            Extracting claims from segments in parallel, then formalizing in batches.
          </p>
        </div>
      )}

      {formalizationData && (
        <section style={panelStyle}>
          <h2 style={sectionTitleStyle}>3. Review</h2>
          <p style={{ margin: '0 0 12px', color: '#444' }}>
            Found {formalizationData.axioms?.length || 0} formalized claims
            {formalizeType ? ` (${FORMALIZE_OPTIONS.find((o) => o.type === formalizeType)?.label.toLowerCase()})` : ''}.
          </p>
          {(formalizationData.download_url || formalizationData.output_pdf_path) && (
            <div style={{ margin: '0 0 16px' }}>
              <a
                href={
                  formalizationData.download_url
                    ? formalizationData.download_url                    // preferred: served from /files/...
                    : `/download?path=${encodeURIComponent(formalizationData.output_pdf_path)}` // fallback
                }
                target="_blank" rel="noopener noreferrer"
                style={{ display: 'inline-block', padding: '10px 20px', background: '#495057', color: '#fff', textDecoration: 'none', borderRadius: 6 }}
              >📄 Download Result PDF</a>
            </div>
          )}
          {formalizationData.axioms?.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>Filter by risk tier:</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  {TIER_FILTERS.map((t) => (
                    <button
                      key={t}
                      onClick={() => setTierFilter(t)}
                      style={{
                        padding: '4px 10px', fontSize: 13, borderRadius: 4, cursor: 'pointer',
                        border: '1px solid #999',
                        background: tierFilter === t ? '#333' : '#fff',
                        color: tierFilter === t ? '#fff' : '#333',
                      }}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ maxHeight: 600, overflowY: 'auto', border: '1px solid #ddd', borderRadius: 6, padding: 10, background: '#f9f9f9' }}>
                {visibleClaims.map((claim) => (
                  <ClaimCard
                    key={claim.id}
                    claim={claim}
                    decision={decisions[claim.id]}
                    onDecide={handleDecide}
                  />
                ))}
                {visibleClaims.length === 0 && (
                  <p style={{ fontStyle: 'italic', color: '#666', margin: 0 }}>No claims match this filter.</p>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

const panelStyle = {
  background: '#fff',
  border: '1px solid #e3e5e8',
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
};

const sectionTitleStyle = {
  margin: '0 0 12px',
  fontSize: 17,
};

const btnStyle = {
  padding: '10px 18px',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: 15,
  fontWeight: 600,
  textAlign: 'left',
};
