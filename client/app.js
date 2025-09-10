import React, { useState } from 'react';
import FileUpload from './fileupload';

function App() {
  const [fileUrl, setFileUrl] = useState(null);
  const [formatType, setFormatType] = useState(null);
  const [formalizationData, setFormalizationData] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);

  const onFileUpload = async (file) => {
    setError(null);
    setFormalizationData(null);
    
    const formData = new FormData();
    formData.append('file', file);

    const API_URL = '' // process.env.REACT_APP_API_URL || 'http://localhost:3000'; <---- for dev purposes

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      if (data.fileUrl) {
        setFileUrl(data.fileUrl);
      } else {
        setError('Upload failed. Please try again.');
      }
    } catch (err) {
      setError('Upload failed. Please check if the server is running.');
    }
  };

  const handleFormalize = async (type) => {
    if (!fileUrl) return;
    
    setIsProcessing(true);
    setError(null);
    setFormatType(type);

    try {
      const response = await fetch(`${API_URL}/formalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          fileUrl, 
          formatType: type,
          useParallel: true,  // Enable parallel processing
          maxWorkers: 5       // Use 5 parallel workers
        }),
      });
      
      const data = await response.json();
      
      if (data.error) {
        setError(data.error);
      } else {
        setFormalizationData(data);
      }
    } catch (err) {
      setError('Formalization failed. Please try again.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div style={{margin: '40px', fontFamily: 'Arial, sans-serif', color: '#111', background: '#fff'}}>
      <h1>Wittgenstein</h1>
      <p>Upload a PDF or EPUB file to extract and formalize philosophical claims.</p>
      
      <FileUpload onFileUpload={onFileUpload} />
      
      {error && (
        <div style={{color: 'red', margin: '10px 0', padding: '10px', backgroundColor: '#ffe6e6', border: '1px solid #ffcccc', borderRadius: '4px'}}>
          {error}
        </div>
      )}
      
      {fileUrl && !isProcessing && (
        <div style={{margin: '20px 0'}}>
          <h2>Choose Formalization Type</h2>
          <div style={{display: 'flex', gap: '10px'}}>
            <button 
              onClick={() => handleFormalize('logic')}
              style={{
                padding: '10px 20px',
                backgroundColor: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '16px'
              }}
            >
              Formal Logic
            </button>
            <button 
              onClick={() => handleFormalize('english')}
              style={{
                padding: '10px 20px',
                backgroundColor: '#28a745',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '16px'
              }}
            >
              English Formalization
            </button>
          </div>
        </div>
      )}

      {isProcessing && (
        <div style={{margin: '20px 0', padding: '20px', backgroundColor: '#f8f9fa', border: '1px solid #dee2e6', borderRadius: '4px'}}>
          <p>Processing file, it may take a few minutes...</p>
          <p style={{fontSize: '14px', color: '#666', marginTop: '5px'}}>
            Extracting claims from segments in parallel, then formalizing in batches.
          </p>
        </div>
      )}

      {formalizationData && (
        <div style={{marginTop: '20px'}}>
          <h3>Formalization Results</h3>
          <p>Found {formalizationData.axioms?.length || 0} formalized claims</p>
          
          {formalizationData.output_pdf_path && (
            <div style={{margin: '10px 0'}}>
              <a 
                href={`/download?path=${encodeURIComponent(formalizationData.output_pdf_path)}`} // {`${process.env.REACT_APP_API_URL || 'http://localhost:3000'}/download?path=${encodeURIComponent(formalizationData.output_pdf_path)}`} <------ for dev purposes
                target="_blank" 
                rel="noopener noreferrer"
                style={{
                  display: 'inline-block',
                  padding: '10px 20px',
                  backgroundColor: '#dc3545',
                  color: 'white',
                  textDecoration: 'none',
                  borderRadius: '4px',
                  fontSize: '16px'
                }}
              >
                📄 Download Result PDF
              </a>
            </div>
          )}
          
          {formalizationData.axioms && formalizationData.axioms.length > 0 && (
            <div style={{marginTop: '20px'}}>
              <h4>Sample Claims:</h4>
              <div style={{maxHeight: '400px', overflowY: 'auto', border: '1px solid #ddd', padding: '10px', backgroundColor: '#f9f9f9'}}>
                {formalizationData.axioms.slice(0, 5).map((axiom, index) => (
                  <div key={index} style={{marginBottom: '15px', padding: '10px', backgroundColor: 'white', borderRadius: '4px'}}>
                    <strong>English:</strong> {axiom.english}<br/>
                    <strong>Formal:</strong> {axiom.formal}
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

export default App;
