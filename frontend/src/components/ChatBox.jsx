import { useState, useRef, useEffect } from 'react';
import { apiUrl } from '../api';
import { readEvents } from '../stream';

const greeting = { sender: 'ai', text: '您好！您可以詢問文件內容，或按「摘要文件」整理重點。' };

export default function ChatBox({ documentId, onCitationsChange, disabled }) {
    const storageKey = `pdf-agent-thread:${documentId}`;
    const [threadId, setThreadId] = useState(() => {
        const saved = localStorage.getItem(storageKey);
        if (saved && /^[0-9a-f-]{36}$/i.test(saved)) return saved;
        const id = crypto.randomUUID();
        localStorage.setItem(storageKey, id);
        return id;
    });
    const [messages, setMessages] = useState([greeting]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [restoring, setRestoring] = useState(true);
    const [steps, setSteps] = useState([]);
    const [hasSummary, setHasSummary] = useState(false);
    const bottomRef = useRef(null);
    const controllerRef = useRef(null);
    const sendingRef = useRef(false);

    useEffect(() => {
        const controller = new AbortController();
        fetch(apiUrl(`/api/threads/${threadId}?document_id=${documentId}`), { signal: controller.signal })
            .then(async response => {
                if (!response.ok) throw new Error('無法恢復對話記憶');
                return response.json();
            })
            .then(data => {
                const restored = [...data.messages];
                const last = restored.length - 1;
                if (data.result && restored[last]?.sender === 'ai' && restored[last]?.text === data.result.answer) {
                    restored[last] = { ...restored[last], citations: data.result.citations };
                }
                setMessages(restored.length ? restored : [greeting]);
                setHasSummary(data.has_summary);
                if (data.result) onCitationsChange(data.result.citations, data.result.primary_citation_id);
            })
            .catch(error => {
                if (error.name !== 'AbortError') setMessages([greeting, { sender: 'ai', text: error.message }]);
            })
            .finally(() => { if (!controller.signal.aborted) setRestoring(false); });
        return () => controller.abort();
    }, [threadId, documentId, onCitationsChange]);

    useEffect(() => () => controllerRef.current?.abort(), []);
    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, steps]);

    function newChat() {
        const id = crypto.randomUUID();
        localStorage.setItem(storageKey, id);
        setMessages([greeting]);
        setSteps([]);
        setHasSummary(false);
        setRestoring(true);
        onCitationsChange([], null);
        setThreadId(id);
    }

    async function send(question = input) {
        if (!question.trim() || sendingRef.current || disabled || restoring) return;
        sendingRef.current = true;
        controllerRef.current = new AbortController();
        const trace = [];
        setInput('');
        setLoading(true);
        setSteps([]);
        setMessages(previous => [...previous, { sender: 'user', text: question }]);
        onCitationsChange([], null);
        try {
            const response = await fetch(apiUrl('/api/chat/stream'), {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, document_id: documentId, thread_id: threadId }),
                signal: controllerRef.current.signal,
            });
            await readEvents(response, event => {
                if (event.type === 'status') {
                    trace.push(event);
                    setSteps([...trace]);
                    if (event.stage === 'memory_summarized') setHasSummary(true);
                } else if (event.type === 'result') {
                    setMessages(previous => [...previous, { sender: 'ai', text: event.answer,
                        citations: event.citations, primaryId: event.primary_citation_id, steps: [...trace] }]);
                    onCitationsChange(event.citations, event.primary_citation_id);
                }
            });
        } catch (error) {
            if (error.name !== 'AbortError') {
                setMessages(previous => [...previous, { sender: 'ai', text: error.message, steps: [...trace] }]);
            }
        } finally {
            sendingRef.current = false;
            setLoading(false);
        }
    }

    const busy = loading || restoring || disabled;
    return (
        <div className="chat-panel">
            <div className="chat-header"><span className="status-dot" />AI 文件助理</div>
            <div className="chat-toolbar">
                <button disabled={busy} onClick={() => send('請摘要整份文件，整理重點、重要數值、適用條件與限制。')}>摘要文件</button>
                <button disabled={busy} onClick={newChat}>新聊天</button>
                <span>{hasSummary ? '對話記憶已壓縮' : '對話記憶已啟用'}</span>
            </div>
            <div className="chat-messages" aria-live="polite">
                {messages.map((message, index) => (
                    <div key={index} className={`message ${message.sender}`}>
                        <div className="message-text">{message.text}</div>
                        {!!message.citations?.length && <div className="citation-list">
                            {message.citations.map(citation => <button key={citation.block_id}
                                onClick={() => onCitationsChange(message.citations, citation.block_id)}
                                title={citation.text}>第 {citation.page} 頁 · {citation.block_id}</button>)}
                        </div>}
                        {!!message.steps?.length && <details className="agent-trace">
                            <summary>查看執行過程</summary>
                            <ol>{message.steps.map((step, i) => <li key={i}>{step.label}</li>)}</ol>
                        </details>}
                    </div>
                ))}
                {restoring && <div className="message ai">正在恢復對話記憶…</div>}
                {loading && <div className="message ai agent-progress">
                    <strong>處理進度</strong>
                    <ol>{steps.map((step, i) => <li key={i}>{step.label}</li>)}</ol>
                    <span>處理中…</span>
                </div>}
                <div ref={bottomRef} />
            </div>
            <form className="chat-input-area" onSubmit={event => { event.preventDefault(); send(); }}>
                <input className="chat-input" aria-label="文件問題" placeholder="詢問文件，或接著追問…"
                    onKeyDown={event => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }}
                    value={input} onChange={event => setInput(event.target.value)} disabled={busy} />
                <button className="send-btn" disabled={busy || !input.trim()} aria-label="送出問題">➤</button>
            </form>
        </div>
    );
}
