import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import PdfViewer from './components/PdfViewer';
import ChatBox from './components/ChatBox';
import './index.css';
import { apiUrl } from './api';

function App() {
  const [pdfFileUrl, setPdfFileUrl] = useState(null);
  const [documentId, setDocumentId] = useState(null);
  const [citations, setCitations] = useState([]);
  const [primaryId, setPrimaryId] = useState(null);
  const [focusVersion, setFocusVersion] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Check if a file is already active on the backend when app loads
  useEffect(() => {
    const fetchCurrentFile = async () => {
      try {
        const response = await axios.get(apiUrl('/api/current-file'));
        if (response.data && response.data.url) {
          setPdfFileUrl(apiUrl(response.data.url));
          setDocumentId(response.data.document_id);
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

    setCitations([]);
    setPrimaryId(null);
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(apiUrl('/api/upload'), formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      // Set the pdf file URL returned by backend (static path)
      setPdfFileUrl(apiUrl(response.data.url));
      setDocumentId(response.data.document_id);
    } catch (error) {
      console.error("Error uploading file:", error);
      alert(error.response?.data?.detail || "上傳失敗，請確認後端是否正常運作");
      setPdfFileUrl(null);
      setDocumentId(null);
    } finally {
      setIsUploading(false);
      event.target.value = '';
    }
  };

  const handleCitationsChange = useCallback((nextCitations, nextPrimaryId) => {
    setCitations(nextCitations || []);
    setPrimaryId(nextPrimaryId);
    setFocusVersion(value => value + 1);
  }, []);

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
            <PdfViewer key={documentId} fileUrl={pdfFileUrl} citations={citations} primaryId={primaryId} focusVersion={focusVersion} />
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
      {documentId ? <ChatBox key={documentId} documentId={documentId}
        onCitationsChange={handleCitationsChange} disabled={isUploading} /> :
        <div className="chat-panel"><div className="chat-header">AI 文件助理</div>
          <div className="chat-messages">請先上傳 PDF 文件。</div></div>}
    </div>
  );
}

export default App;

