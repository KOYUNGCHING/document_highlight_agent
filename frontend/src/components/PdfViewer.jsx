import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

class ErrorBoundary extends React.Component {
    constructor(props) { super(props); this.state = { hasError: false, error: null }; }
    static getDerivedStateFromError(error) { return { hasError: true, error }; }
    render() {
        if (this.state.hasError) {
            return <div style={{ padding: 20, color: 'red' }}><pre>{this.state.error?.toString()}</pre></div>;
        }
        return this.props.children;
    }
}

// Build sub-phrases from highlight strings (split on sentence boundaries, remove list numbering)
function buildSubPhrases(highlights) {
    const phrases = [];
    (highlights || []).forEach(phrase => {
        if (!phrase || typeof phrase !== 'string') return;
        phrase.split(/[\n\r。；：，]/g).forEach(part => {
            const cleaned = part.trim()
                .replace(/^([一二三四五六七八九十百]+[、.．])|^(\d+[、.．])/g, '')
                .trim();
            if (cleaned.length >= 4) phrases.push(cleaned);
        });
    });
    return Array.from(new Set(phrases));
}

// Normalize a string by removing all punctuation/spaces (for fuzzy matching)
function normalize(str) {
    return str.replace(/[\s\.,\/#!$%\^&\*;:{}=\-_`~()?"'，。：；「」『』、（）\n\r]/g, '').toLowerCase();
}

// Attempt to match a phrase in a single text layer, highlight matching spans, return first span or null
function matchPhraseInLayer(layer, normPhrase) {
    // Select only leaf span elements (spans that contain no other spans) so we target actual text layout nodes
    const spans = Array.from(layer.querySelectorAll('span')).filter(s => s.querySelectorAll('span').length === 0);
    if (!spans.length) return null;

    let fullText = '';
    const charToSpan = [];
    spans.forEach(span => {
        const t = span.textContent || '';
        for (let i = 0; i < t.length; i++) charToSpan.push(span);
        fullText += t;
    });

    let normText = '';
    const normToOrig = [];
    for (let i = 0; i < fullText.length; i++) {
        if (!/[\s\.,\/#!$%\^&\*;:{}=\-_`~()?"'，。：；「」『』、（）\n\r]/.test(fullText[i])) {
            normText += fullText[i].toLowerCase();
            normToOrig.push(i);
        }
    }

    const idx = normText.indexOf(normPhrase);
    if (idx === -1) return null;

    const origStart = normToOrig[idx];
    const origEnd = normToOrig[idx + normPhrase.length - 1];
    if (origEnd === undefined) return null;

    const matched = new Set();
    for (let i = origStart; i <= origEnd; i++) {
        if (charToSpan[i]) matched.add(charToSpan[i]);
    }

    let firstSpan = null;
    matched.forEach(span => {
        // Set data-highlighted so the CSS selector kicks in
        span.setAttribute('data-highlighted', 'true');
        // Also set inline style as fallback in case CSS specificity is lost
        span.style.setProperty('background-color', 'rgba(251, 191, 36, 0.65)', 'important');
        span.style.setProperty('border-bottom', '2px solid #f59e0b', 'important');
        span.style.setProperty('border-radius', '2px', 'important');
        if (!firstSpan) firstSpan = span;
    });
    console.log(`[PdfViewer] matchPhraseInLayer: matched ${matched.size} spans for "${normPhrase.slice(0, 20)}..."`);
    return firstSpan;
}

// Iterate text layers (= pages, in DOM order) FIRST, then phrases within each layer.
// This guarantees firstEl is always the topmost (earliest-page) match.
function applyHighlightsToDOM(normPhrases) {
    const textLayers = Array.from(document.querySelectorAll('.react-pdf__Page__textContent'));
    let firstEl = null;

    for (const layer of textLayers) {
        for (const normPhrase of normPhrases) {
            const el = matchPhraseInLayer(layer, normPhrase);
            if (el && !firstEl) firstEl = el;
        }
    }
    return firstEl;
}


// Clear all applied highlights from the DOM
function clearAllHighlights() {
    document.querySelectorAll('[data-highlighted="true"]').forEach(el => {
        el.style.removeProperty('background-color');
        el.style.removeProperty('border-bottom');
        el.style.removeProperty('border-radius');
        el.removeAttribute('data-highlighted');
    });
    document.querySelectorAll('.page-glow-active').forEach(el => el.classList.remove('page-glow-active'));
}

const PdfViewerInner = ({ fileUrl, highlights, targetPage }) => {
    const [numPages, setNumPages] = useState(null);
    const [containerWidth, setContainerWidth] = useState(600);
    const containerRef = useRef(null);
    const hasScrolledRef = useRef(false);
    const activeHighlightsRef = useRef([]);  // Store active highlights between renders

    // Measure container width
    useEffect(() => {
        const measure = () => {
            if (containerRef.current) setContainerWidth(containerRef.current.clientWidth - 4);
        };
        measure();
        const ro = new ResizeObserver(measure);
        if (containerRef.current) ro.observe(containerRef.current);
        return () => ro.disconnect();
    }, []);

    // Re-apply highlights across all currently rendered text layers
    const applyHighlights = useCallback((phrases, scrollToFirst) => {
        const subPhrases = buildSubPhrases(phrases);
        if (!subPhrases.length) return;

        const normPhrases = subPhrases
            .map(p => normalize(p))
            .filter(p => p.length >= 2);
        if (!normPhrases.length) return;

        // Uses page-first iteration: firstEl is guaranteed to be the topmost DOM match
        const firstEl = applyHighlightsToDOM(normPhrases);

        console.log('[PdfViewer] applyHighlights: found firstEl=', !!firstEl, 'scrollToFirst=', scrollToFirst, 'hasScrolled=', hasScrolledRef.current);

        if (scrollToFirst && !hasScrolledRef.current) {
            let scrolled = false;
            if (targetPage) {
                const targetPageEl = document.querySelector(`.react-pdf__Page[data-page-number="${targetPage}"]`);
                if (targetPageEl) {
                    const layer = targetPageEl.querySelector('.react-pdf__Page__textContent');
                    if (layer) {
                        const targetEl = layer.querySelector('[data-highlighted="true"]');
                        if (targetEl) {
                            hasScrolledRef.current = true;
                            scrolled = true;
                            setTimeout(() => {
                                targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                targetPageEl.classList.add('page-glow-active');
                                setTimeout(() => targetPageEl.classList.remove('page-glow-active'), 3000);
                            }, 100);
                        }
                    }
                }
            }

            if (!scrolled && !targetPage) {
                // Fallback to first matched element in DOM if no targetPage is specified
                if (firstEl) {
                    hasScrolledRef.current = true;
                    setTimeout(() => {
                        firstEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        const pageDiv = firstEl.closest('.react-pdf__Page');
                        if (pageDiv) {
                            pageDiv.classList.add('page-glow-active');
                            setTimeout(() => pageDiv.classList.remove('page-glow-active'), 3000);
                        }
                    }, 100);
                }
            }
        }
    }, [targetPage]);

    // When highlights change from a new question
    useEffect(() => {
        clearAllHighlights();
        hasScrolledRef.current = false;
        activeHighlightsRef.current = highlights || [];

        if (!highlights || highlights.length === 0) return;

        // Apply immediately (for pages already in DOM), then again after short delay
        applyHighlights(highlights, true);
        const t = setTimeout(() => applyHighlights(highlights, true), 600);
        return () => clearTimeout(t);
    }, [highlights, applyHighlights]);

    const onDocumentLoadSuccess = useCallback(({ numPages }) => setNumPages(numPages), []);

    // Called by react-pdf when each individual page's text layer finishes rendering
    const onPageRenderSuccess = useCallback(() => {
        const current = activeHighlightsRef.current;
        if (current && current.length > 0) {
            applyHighlights(current, true);
        }
    }, [applyHighlights]);

    return (
        <div
            ref={containerRef}
            style={{ height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px' }}
        >
            <Document
                file={fileUrl}
                onLoadSuccess={onDocumentLoadSuccess}
                loading={<p style={{ color: 'var(--text-light)', padding: '40px' }}>載入中...</p>}
                error={<p style={{ color: 'red', padding: '20px' }}>無法載入 PDF 文件</p>}
            >
                {Array.from({ length: numPages || 0 }, (_, i) => (
                    <div
                        key={`page-${i + 1}`}
                        style={{
                            marginBottom: '12px',
                            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                            minHeight: `${containerWidth * 1.414}px`,
                            backgroundColor: '#fff'
                        }}
                    >
                        <Page
                            pageNumber={i + 1}
                            width={containerWidth}
                            onRenderSuccess={onPageRenderSuccess}
                            onRenderTextLayerSuccess={onPageRenderSuccess}
                        />
                    </div>
                ))}
            </Document>
        </div>
    );
};

export default function PdfViewer(props) {
    return (
        <ErrorBoundary>
            <PdfViewerInner {...props} />
        </ErrorBoundary>
    );
}
