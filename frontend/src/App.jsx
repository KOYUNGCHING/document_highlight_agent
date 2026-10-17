import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import PdfViewer from './components/PdfViewer';
import ChatBox from './components/ChatBox';
import './index.css';

function App() {
  const [pdfFileUrl, setPdfFileUrl] = useState(null);
  const [highlights, setHighlights] = useState([]);
  const [targetPage, setTargetPage] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Check if a file is already active on the backend when app loads
  useEffect(() => {
    const fetchCurrentFile = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/current-file');
        if (response.data && response.data.url) {
          setPdfFileUrl(response.data.url);
        }
      } catch (error) {
        console.error("Error fetching current file:", error);
      }
    };
    fetchCurrentFile();
  }, []);

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setHighlights([]);
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('http://localhost:8000/api/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      // Set the pdf file URL returned by backend (static path)
      setPdfFileUrl(response.data.url);
    } catch (error) {
      console.error("Error uploading file:", error);
      alert("上傳失敗，請確認後端是否正常運作");
      setPdfFileUrl(null);
    } finally {
      setIsUploading(false);
    }
  };

  const handleHighlightsChange = (newHighlights, newTargetPage) => {
    setHighlights(newHighlights);
    setTargetPage(newTargetPage);
  };

  return (
    <div className="app-container">
      {/* Left Panel: PDF Viewer */}
      <div className="pdf-panel">
        <div className="pdf-header">
          <span>📄 文件檢視器</span>
          {pdfFileUrl && (
            <button className="upload-btn" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => fileInputRef.current.click()}>
              重新上傳
            </button>
          )}
        </div>
        <div className="pdf-content">
          {!pdfFileUrl && !isUploading && (
            <div className="upload-overlay">
              <h2 style={{ marginBottom: '16px', color: 'var(--primary-blue)' }}>PDF 智慧搜尋系統</h2>
              <p style={{ marginBottom: '24px', color: 'var(--text-light)' }}>請上傳一份 PDF 開始解析</p>
              <button className="upload-btn" onClick={() => fileInputRef.current.click()}>
                選擇檔案上傳
              </button>
            </div>
          )}
          {isUploading && (
            <div className="upload-overlay" style={{ background: 'rgba(255, 255, 255, 0.8)' }}>
              <h3>正在解析與讀取文件...</h3>
            </div>
          )}
          {pdfFileUrl && !isUploading && (
            <PdfViewer fileUrl={pdfFileUrl} highlights={highlights} targetPage={targetPage} />
          )}
          <input 
            type="file" 
            accept="application/pdf" 
            ref={fileInputRef} 
            className="upload-input" 
            onChange={handleFileUpload} 
          />
        </div>
      </div>

      {/* Right Panel: Chat Box */}
      <ChatBox 
        onHighlightsChange={handleHighlightsChange} 
        isPdfUploaded={!!pdfFileUrl && !isUploading} 
      />
    </div>
  );
}

export default App;

