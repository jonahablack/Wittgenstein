// client/src/App.jsx
import React, { useState } from 'react';
import FileUpload from './FileUpload.jsx';

export default function App() {
  const [fileId, setFileId] = useState(null);
  const [formalizationData, setFormalizationData] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);

  const onFileUpload = async (file) => {
    setError(null);
    setFormalizationData(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.fileId) setFileId(data.fileId);
      else setError(data.error || 'Upload failed.');
    } catch {
      setError('Upload failed. Please try again.');
    }
  };

  const handleFormalize = async (type) => {
    if (!fileId) return;
    setIsProcessing(true);
    setError(null);
    try {
      const res = await fetch('/formalize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fileId, formatType: type, useParallel: true, maxWorkers: 5 }),
      });
      const data = await res.json();
      if (data.error) setError(data.error);
      else setFormalizationData(data);
    } catch {
      setError('Formalization failed. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div style={{margin: 40, fontFamily: 'Arial, sans-serif'}}>
      <h1>Wittgenstein</h1>
      <p>Upload a PDF or EPUB file to extract and formalize philosophical claims.</p>

      <FileUpload onFileUpload={onFileUpload} />

      {error && (
        <div style={{color: 'red', margin: '10px 0', padding: 10, background: '#ffe6e6', border: '1px solid #ffcccc', borderRadius: 4}}>
          {error}
        </div>
      )}

      {fileId && !isProcessing && (
        <div style={{margin: '20px 0'}}>
          <h2>Choose Formalization Type</h2>
          <div style={{display: 'flex', gap: 10}}>
            <button onClick={() => handleFormalize('logic')} style={btnStyle}>Formal Logic</button>
            <button onClick={() => handleFormalize('english')} style={{...btnStyle, backgroundColor: '#28a745'}}>English Formalization</button>
          </div>
        </div>
      )}

      {isProcessing && (
        <div style={{margin: '20px 0', padding: 20, background: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: 4}}>
          <p>Processing file, it may take a few minutes...</p>
          <p style={{fontSize: 14, color: '#666', marginTop: 5}}>
            Extracting claims from segments in parallel, then formalizing in batches.
          </p>
        </div>
      )}

      {formalizationData && (
        <div style={{marginTop: 20}}>
          <h3>Formalization Results</h3>
          <p>Found {formalizationData.axioms?.length || 0} formalized claims</p>
          {formalizationData.output_pdf_path && (
            <div style={{margin: '10px 0'}}>
              <a
                href={`/download?path=${encodeURIComponent(formalizationData.output_pdf_path)}`}
                target="_blank" rel="noopener noreferrer"
                style={{display: 'inline-block', padding: '10px 20px', background: '#dc3545', color: '#fff', textDecoration: 'none', borderRadius: 4}}
              >📄 Download Result PDF</a>
            </div>
          )}
          {formalizationData.axioms?.length > 0 && (
            <div style={{marginTop: 20}}>
              <h4>Sample Claims:</h4>
              <div style={{maxHeight: 400, overflowY: 'auto', border: '1px solid #ddd', padding: 10, background: '#f9f9f9'}}>
                {formalizationData.axioms.slice(0, 5).map((a, i) => (
                  <div key={i} style={{marginBottom: 15, padding: 10, background: '#fff', borderRadius: 4}}>
                    <strong>English:</strong> {a.english}<br/>
                    <strong>Formal:</strong> {a.formal}
                  </div>
                ))}
                {formalizationData.axioms.length > 5 && (
                  <p style={{fontStyle: 'italic', color: '#666'}}>
                    ... and {formalizationData.axioms.length - 5} more claims
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const btnStyle = {
  padding: '10px 20px',
  backgroundColor: '#007bff',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 16,
};

