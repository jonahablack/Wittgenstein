import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';

const FileUpload = ({ onFileUpload }) => {
  const [uploadedFileName, setUploadedFileName] = useState(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const onDrop = (acceptedFiles) => {
    const uploadedFile = acceptedFiles[0];
    setUploadedFileName(uploadedFile.name);
    onFileUpload(uploadedFile);
  };

  const { getRootProps, getInputProps, isDragActive: dropzoneIsDragActive } = useDropzone({ 
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/epub+zip': ['.epub']
    },
    multiple: false
  });

  const dropzoneStyles = {
    border: isDragActive || dropzoneIsDragActive ? '2px dashed #007bff' : '2px dashed #cccccc',
    borderRadius: '8px',
    padding: '40px 20px',
    textAlign: 'center',
    cursor: 'pointer',
    backgroundColor: isDragActive || dropzoneIsDragActive ? '#f8f9ff' : '#fafafa',
    transition: 'all 0.3s ease',
    minHeight: '150px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center'
  };

  return (
    <div style={{margin: '20px'}}>
      <div {...getRootProps()} style={dropzoneStyles}>
        <input {...getInputProps()} />
        <div style={{fontSize: '48px', marginBottom: '10px'}}>📄</div>
        <p style={{fontSize: '18px', margin: '0 0 10px 0', fontWeight: 'bold'}}>
          {isDragActive || dropzoneIsDragActive ? 'Drop your file here!' : 'Drag & drop your PDF or EPUB here'}
        </p>
        <p style={{fontSize: '14px', margin: '0', color: '#666'}}>
          or click to browse files
        </p>
        <p style={{fontSize: '12px', margin: '10px 0 0 0', color: '#999'}}>
          Supports: PDF, EPUB files
        </p>
      </div>
      {uploadedFileName && (
        <div style={{
          marginTop: '15px',
          padding: '10px',
          backgroundColor: '#d4edda',
          border: '1px solid #c3e6cb',
          borderRadius: '4px',
          color: '#155724'
        }}>
          ✅ File '{uploadedFileName}' uploaded successfully!
        </div>
      )}
    </div>
  );
};

export default FileUpload;
