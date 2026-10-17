import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const ChatBox = ({ onHighlightsChange, isPdfUploaded }) => {
    const [messages, setMessages] = useState([{
        sender: 'ai',
        text: '您好！我是您的 PDF 智慧助理。請先上傳或選擇文件後，即可開始詢問關於文件的內容。'
    }]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSend = async () => {
        if (!inputValue.trim()) return;

        const userMsg = { sender: 'user', text: inputValue };
        setMessages(prev => [...prev, userMsg]);
        setInputValue('');
        setIsLoading(true);

        try {
            const response = await axios.post('http://localhost:8000/api/chat', {
                question: userMsg.text
            });
            
            const aiMsg = { 
                sender: 'ai', 
                text: response.data.answer 
            };
            
            setMessages(prev => [...prev, aiMsg]);
            
            if (response.data.highlights && response.data.highlights.length > 0) {
                onHighlightsChange(response.data.highlights, response.data.target_page);
            } else {
                onHighlightsChange([], null);
            }
            
        } catch (error) {
            console.error("Error sending message:", error);
            setMessages(prev => [...prev, { sender: 'ai', text: '抱歉，發生了錯誤，請確認後端服務是否正常運作。' }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            handleSend();
        }
    };

    return (
        <div className="chat-panel">
            <div className="chat-header">
                <div className="status-dot"></div>
                AI 文件助理
            </div>
            
            <div className="chat-messages">
                {messages.map((msg, index) => (
                    <div key={index} className={`message ${msg.sender}`}>
                        {msg.text}
                    </div>
                ))}
                {isLoading && (
                    <div className="message ai">
                        <span style={{ fontStyle: 'italic', color: 'var(--text-light)' }}>思考中...</span>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-area">
                <input
                    type="text"
                    className="chat-input"
                    placeholder={isPdfUploaded ? "輸入您的問題... (例如：皮肌移位倍數？)" : "請先上傳 PDF"}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={!isPdfUploaded || isLoading}
                />
                <button 
                    className="send-btn" 
                    onClick={handleSend}
                    disabled={!isPdfUploaded || isLoading || !inputValue.trim()}
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </div>
        </div>
    );
};

export default ChatBox;
