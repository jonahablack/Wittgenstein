// client/src/views/BatchReview.jsx
// Mode 1: whole-document ("batch") review -- the original Wittgenstein
// flow. Upload, pick chunking mode + formalization type, then review every
// extracted claim sorted and filterable by risk tier.
import React, { useState, useRef } from 'react';
import FileUpload from '../FileUpload.jsx';
import ClaimCard from '../ClaimCard.jsx';
import { fetchJson, postJson } from '../api.js';
import {
  TIER_ORDER, TIER_FILTERS, TIER_LEGEND,
  panelStyle, sectionTitleStyle, btnStyle, errorBoxStyle,
} from '../tiers.js';

const FORMALIZE_OPTIONS = [
  { type: 'logic', label: 'Formal Logic', desc: 'symbolic logic only', color: '#0d6efd' },
  { type: 'english', label: 'English Formalization', desc: 'structured English only', color: '#198754' },
  { type: 'both', label: 'Both', desc: 'logic + English side by side', color: '#6f42c1' },
];

const CHUNKING_OPTIONS = [
  { mode: 'propositional', label: 'Propositional', desc: 'split into individual propositions (default)' },
  { mode: 'passage', label: 'Passage', desc: 'keep larger passages together' },
];

export default function BatchReview({ onDocumentReady }) {
  const [fileId, setFileId] = useState(null);
  const [uploadedFileName, setUploadedFileName] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [formalizationData, setFormalizationData] = useState(null);
  const [resultsByType, setResultsByType] = useState({});
  const [formalizeType, setFormalizeType] = useState(null);
  const [chunkingMode, setChunkingMode] = useState('propositional');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [tierFilter, setTierFilter] = useState('All');
  const [decisions, setDecisions] = useState({});
  const formalizeAbortRef = useRef(null);

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

  const onFileUpload = async (file) => {
    // A wrong-file upload while a formalization is still in flight is exactly
    // the case this guards against: without this, a stale response for the
    // old file could still land after the new one starts and clobber it.
    formalizeAbortRef.current?.abort();
    setIsProcessing(false);

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
      const data = await fetchJson('/upload', { method: 'POST', body: formData });
      if (!data.fileId) throw new Error('Upload failed: server returned no fileId.');
      setFileId(data.fileId);
      setUploadedFileName(file.name);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleFormalize = async (type) => {
    if (!fileId) return;
    setError(null);
    setFormalizeType(type);

    // Already generated this formalization (for this chunking mode) for the
    // current file -- reuse it instead of re-running claim extraction + LLM
    // calls from scratch. The cache key includes the chunking mode because
    // propositional vs. passage chunking produces different claim sets.
    const cacheKey = `${chunkingMode}:${type}`;
    const cached = resultsByType[cacheKey];
    if (cached) {
      setFormalizationData(cached);
      setTierFilter('All');
      await refreshDecisions();
      return;
    }

    const controller = new AbortController();
    formalizeAbortRef.current = controller;
    setIsProcessing(true);
    try {
      const data = await postJson('/formalize', {
        fileId,
        formatType: type,
        chunkingMode,
        useParallel: true,
        maxWorkers: 5,
      }, { signal: controller.signal });
      setResultsByType((prev) => ({ ...prev, [cacheKey]: data }));
      setFormalizationData(data);
      setTierFilter('All');
      if (data.documentId) onDocumentReady?.(data.documentId, uploadedFileName);
      await refreshDecisions();
    } catch (err) {
      // AbortError means handleCancel already set its own message -- don't
      // stomp on it with a generic failure message.
      if (err.name !== 'AbortError') {
        setError(err.message);
      }
    } finally {
      setIsProcessing(false);
      formalizeAbortRef.current = null;
    }
  };

  const handleCancel = () => {
    formalizeAbortRef.current?.abort();
    setIsProcessing(false);
    setFormalizeType(null);
    setError(
      'Cancelled. Note: the server may briefly keep working on the request '
      + 'that was already sent, but its result will be ignored.'
    );
  };

  const handleDecide = async (claimId, decision) => {
    setDecisions((prev) => ({ ...prev, [claimId]: decision }));
    try {
      await postJson('/review', { claimId, decision });
    } catch (err) {
      setError(`Failed to record decision: ${err.message}`);
    }
  };

  const visibleClaims = (formalizationData?.axioms || [])
    .filter((a) => tierFilter === 'All' || a.risk_tier === tierFilter)
    .sort((a, b) => (TIER_ORDER[a.risk_tier] ?? 4) - (TIER_ORDER[b.risk_tier] ?? 4));

  return (
    <div>
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
        <div style={{ marginTop: 14 }}>
          <span style={{ fontWeight: 600, fontSize: 14, display: 'block', marginBottom: 6 }}>
            Chunking mode
          </span>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {CHUNKING_OPTIONS.map(({ mode, label, desc }) => (
              <label key={mode} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="chunking-mode"
                  value={mode}
                  checked={chunkingMode === mode}
                  onChange={() => setChunkingMode(mode)}
                />
                <span><strong>{label}</strong> — {desc}</span>
              </label>
            ))}
          </div>
        </div>
      </section>

      {error && <div style={errorBoxStyle}>{error}</div>}

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
                {label}{resultsByType[`${chunkingMode}:${type}`] ? ' ✓' : ''}
                <span style={{ display: 'block', fontSize: 11, fontWeight: 400, opacity: 0.85 }}>
                  {resultsByType[`${chunkingMode}:${type}`] ? 'already generated — instant switch' : desc}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {isProcessing && (
        <div style={{ margin: '20px 0', padding: 20, background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div>
              <p style={{ margin: 0 }}>Processing file, it may take a few minutes...</p>
              <p style={{ fontSize: 14, color: '#666', marginTop: 5, marginBottom: 0 }}>
                Extracting claims from segments in parallel, then formalizing in batches.
              </p>
            </div>
            <button
              onClick={handleCancel}
              style={{
                padding: '6px 14px', fontSize: 13, borderRadius: 6, cursor: 'pointer',
                border: '1px solid #dc3545', background: '#fff', color: '#dc3545', whiteSpace: 'nowrap',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {formalizationData && (
        <section style={panelStyle}>
          <h2 style={sectionTitleStyle}>3. Review</h2>
          <p style={{ margin: '0 0 12px', color: '#444' }}>
            Found {formalizationData.axioms?.length || 0} claims
            {formalizeType ? ` (${FORMALIZE_OPTIONS.find((o) => o.type === formalizeType)?.label.toLowerCase()})` : ''}.
            {(() => {
              const unformalizedCount = (formalizationData.axioms || [])
                .filter((a) => a.risk_tier === 'Unformalized').length;
              return unformalizedCount > 0
                ? ` ${unformalizedCount} could not be formalized and are shown below with no formal representation.`
                : '';
            })()}
          </p>
          {formalizationData.documentId && (
            <p style={{ margin: '0 0 12px', fontSize: 13, color: '#666' }}>
              Document ID: <code>{formalizationData.documentId}</code> — switch to the
              {' '}<strong>Query review</strong> view to run risk-tiered retrieval against this document.
            </p>
          )}
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
