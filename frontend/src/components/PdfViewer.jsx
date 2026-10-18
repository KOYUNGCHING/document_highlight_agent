import { Component, useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.js', import.meta.url).toString();

class ErrorBoundary extends Component {
    state = { error: null };
    static getDerivedStateFromError(error) { return { error }; }
    render() {
        return this.state.error ? <p role="alert">PDF 顯示失敗，請重新載入。</p> : this.props.children;
    }
}

function PdfViewerInner({ fileUrl, citations, primaryId, focusVersion }) {
    const [numPages, setNumPages] = useState(0);
    const [width, setWidth] = useState(600);
    const containerRef = useRef(null);
    const scrolledRef = useRef('');

    useEffect(() => {
        const container = containerRef.current;
        const observer = new ResizeObserver(() => setWidth(Math.max(200, container.clientWidth - 24)));
        observer.observe(container);
        return () => observer.disconnect();
    }, []);

    function focusCitation() {
        const key = `${focusVersion}:${primaryId}`;
        if (!primaryId || scrolledRef.current === key) return;
        const element = containerRef.current?.querySelector(`[data-citation-id="${CSS.escape(primaryId)}"]`);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            scrolledRef.current = key;
        }
    }

    useEffect(() => {
        const id = requestAnimationFrame(focusCitation);
        return () => cancelAnimationFrame(id);
    });

    return <div className="pdf-scroll" ref={containerRef}>
        <Document file={fileUrl} onLoadSuccess={({ numPages: count }) => setNumPages(count)}
            loading={<p>載入 PDF…</p>} error={<p role="alert">無法載入 PDF 文件</p>}>
            {Array.from({ length: numPages }, (_, index) => <div className="pdf-page-wrap" key={index}>
                <Page pageNumber={index + 1} width={width} onRenderSuccess={focusCitation} />
                <div className="citation-overlay">
                    {citations.filter(c => c.page === index + 1).map(c => <div
                        key={c.block_id} data-citation-id={c.block_id}
                        className={`citation-rect ${c.block_id === primaryId ? 'citation-primary' : ''}`}
                        title={c.text} style={{ left: `${c.rect[0] * 100}%`, top: `${c.rect[1] * 100}%`,
                            width: `${(c.rect[2] - c.rect[0]) * 100}%`,
                            height: `${(c.rect[3] - c.rect[1]) * 100}%` }} />)}
                </div>
            </div>)}
        </Document>
    </div>;
}

export default function PdfViewer(props) {
    return <ErrorBoundary><PdfViewerInner {...props} /></ErrorBoundary>;
}
