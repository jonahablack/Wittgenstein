// client/src/AboutModal.jsx
import React, { useEffect } from 'react';

const SOURCES = [
  {
    id: 'ref1',
    text: 'Revisiting Negation Blindness in Large Language Models',
    venue: 'EMNLP 2025',
    href: 'https://aclanthology.org/2025.emnlp-main.1088/',
    display: 'aclanthology.org/2025.emnlp-main.1088',
  },
  {
    id: 'ref2',
    text: 'SemEval Task: NLI4CT',
    venue: '2023–2024',
    href: 'https://arxiv.org/abs/2305.02993',
    display: 'arxiv.org/abs/2305.02993',
  },
  {
    id: 'ref3',
    text: 'Leung et al., Classifying and Addressing the Diversity of Errors in Retrieval-Augmented Generation Systems',
    venue: '2025',
    href: 'https://arxiv.org/abs/2510.13975',
    display: 'arxiv.org/abs/2510.13975',
  },
  {
    id: 'ref4',
    text: 'Datla et al., Policy→Tests',
    venue: 'AAAI 2026',
    href: 'https://arxiv.org/abs/2512.04408',
    display: 'arxiv.org/abs/2512.04408',
  },
];

function Footnote({ n, refId }) {
  const scrollToRef = (e) => {
    e.preventDefault();
    document.getElementById(refId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  return (
    <sup>
      <a href={`#${refId}`} onClick={scrollToRef} style={{ color: '#3949ab', textDecoration: 'none' }}>
        {n}
      </a>
    </sup>
  );
}

export default function AboutModal({ onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: '40px 20px', zIndex: 1000, overflowY: 'auto',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#fff', borderRadius: 10, maxWidth: 640, width: '100%',
          padding: 28, position: 'relative', color: '#1a1a1a', lineHeight: 1.6,
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute', top: 16, right: 16, border: 'none', background: 'transparent',
            fontSize: 20, cursor: 'pointer', color: '#666', lineHeight: 1, padding: 4,
          }}
        >
        </button>

        <h2 style={{ marginTop: 0, marginBottom: 16, fontSize: 22 }}>About Wittgenstein</h2>

        <p>
          Retrieving information from a body of text is a fundamentally interpretive
          act. But interpretations can be misleading, especially given the presence of
          linguistic complexities. Large language models have documented weaknesses
          untangling these complexities
          <Footnote n="1" refId="ref1" /><Footnote n="2" refId="ref2" />
          <Footnote n="3" refId="ref3" /><Footnote n="4" refId="ref4" />, and any
          assertion, claim, or inference based on information they retrieve is therefore subject to scrutiny.
        </p>

        <p>
          Wittgenstein aims to make retrieved information legible to human
          review. Text segments are flagged for the specific linguistic patterns most
          associated with LLM interpretive error, enabling humans
          to quickly and efficiently review potentially-problematic text
          while reducing <a href="https://www.ibm.com/think/topics/alert-fatigue" target="_blank" rel="noopener noreferrer">alert fatigue</a>.
        </p>

        <p>
          More broadly, this project explores how humans can remain engaged in AI-mediated information
          retrieval by making model failure modes transparent and auditable.
        </p>

        <hr style={{ border: 'none', borderTop: '1px solid #e3e5e8', margin: '20px 0' }} />

        <h3 style={{ fontSize: 15, marginBottom: 10 }}>Sources</h3>
        <ol style={{ paddingLeft: 20, fontSize: 13, color: '#444' }}>
          {SOURCES.map((s, i) => (
            <li key={s.id} id={s.id} style={{ marginBottom: 8 }}>
              <em>{s.text}</em>, {s.venue}.{' '}
              <a href={s.href} target="_blank" rel="noopener noreferrer" style={{ color: '#3949ab' }}>
                {s.display}
              </a>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
