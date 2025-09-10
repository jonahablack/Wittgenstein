// client/src/FileUpload.jsx
import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

export default function FileUpload({ onFileUpload }) {
  const onDrop = useCallback((files) => {
    if (files?.length) onFileUpload(files[0]);
  }, [onFileUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, multiple: false,
    accept: {
      'application/pdf': ['.pdf'],
      'application/epub+zip': ['.epub'],
    },
  });

  return (
    <div {...getRootProps()} style={{
      border: '2px dashed #bbb', padding: 24, borderRadius: 8, textAlign: 'center'
    }}>
      <input {...getInputProps()} />
      {isDragActive ? 'Drop the file here…' : 'Drag & drop a PDF/EPUB, or click to select'}
    </div>
  );
}
