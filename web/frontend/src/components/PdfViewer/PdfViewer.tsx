import { useEffect, useRef, useState, useCallback } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import './PdfViewer.css';

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PdfViewerProps {
  pdfUrl: string | null;
}

const MIN_ZOOM = 25;
const MAX_ZOOM = 300;
const ZOOM_STEP = 25;
const DEFAULT_ZOOM = 75;
const RENDER_SCALE = 1.5;

export default function PdfViewer({ pdfUrl }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pagesContainerRef = useRef<HTMLDivElement>(null);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const pageDivRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const isRenderingRef = useRef<Set<number>>(new Set());
  const observerRef = useRef<IntersectionObserver | null>(null);
  const zoomRef = useRef(DEFAULT_ZOOM);
  const pageViewportsRef = useRef<{ width: number; height: number }[]>([]);

  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const renderPage = useCallback(
    async (pageNum: number, container: HTMLDivElement) => {
      const doc = docRef.current;
      if (!doc || isRenderingRef.current.has(pageNum)) return;

      isRenderingRef.current.add(pageNum);
      try {
        const page: PDFPageProxy = await doc.getPage(pageNum);
        const baseViewport = page.getViewport({ scale: 1 });
        const renderViewport = page.getViewport({ scale: RENDER_SCALE });
        const zf = zoomRef.current / 100;

        const canvas = document.createElement('canvas');
        canvas.width = Math.floor(renderViewport.width);
        canvas.height = Math.floor(renderViewport.height);
        canvas.style.width = `${Math.floor(baseViewport.width * zf)}px`;
        canvas.style.height = `${Math.floor(baseViewport.height * zf)}px`;
        canvas.className = 'pdf-page-canvas';

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        await page.render({
          canvas: canvas as any,
          viewport: renderViewport,
        } as any).promise;

        container.innerHTML = '';
        container.appendChild(canvas);
      } finally {
        isRenderingRef.current.delete(pageNum);
      }
    },
    [],
  );

  // IntersectionObserver — stable, only created once per PDF load
  const setupObserver = useCallback(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const pageNum = Number(entry.target.getAttribute('data-page'));
          if (!pageNum) return;
          if (entry.isIntersecting) {
            const ph = (entry.target as HTMLElement).querySelector('.pdf-page-placeholder');
            if (ph) ph.textContent = '';
            renderPage(pageNum, entry.target as HTMLDivElement);
          }
        });
      },
      { root: container, rootMargin: '200px 0px', threshold: 0 },
    );

    observerRef.current = observer;
    pageDivRefs.current.forEach((div) => observer.observe(div));
  }, [renderPage]);

  // Build page placeholders
  const buildPages = useCallback(
    async (doc: PDFDocumentProxy) => {
      const pagesContainer = pagesContainerRef.current;
      if (!pagesContainer) return;

      pagesContainer.innerHTML = '';
      pageDivRefs.current.clear();
      isRenderingRef.current.clear();
      pageViewportsRef.current = [];

      const zf = zoomRef.current / 100;

      for (let i = 1; i <= doc.numPages; i++) {
        const page = await doc.getPage(i);
        const vp = page.getViewport({ scale: 1 });
        pageViewportsRef.current.push({ width: vp.width, height: vp.height });

        const pageDiv = document.createElement('div');
        pageDiv.className = 'pdf-page-wrapper';
        pageDiv.dataset.page = String(i);
        pageDiv.style.width = `${vp.width * zf}px`;
        pageDiv.style.height = `${vp.height * zf}px`;
        pageDiv.style.margin = '0 auto 8px auto';

        const placeholder = document.createElement('div');
        placeholder.className = 'pdf-page-placeholder';
        placeholder.textContent = String(i);
        pageDiv.appendChild(placeholder);

        pagesContainer.appendChild(pageDiv);
        pageDivRefs.current.set(i, pageDiv);
      }

      setupObserver();
    },
    [setupObserver],
  );

  // Load PDF
  useEffect(() => {
    if (!pdfUrl) {
      docRef.current?.destroy();
      docRef.current = null;
      pageDivRefs.current.clear();
      isRenderingRef.current.clear();
      pageViewportsRef.current = [];
      setTotalPages(0);
      setCurrentPage(1);
      setError(null);
      if (pagesContainerRef.current) pagesContainerRef.current.innerHTML = '';
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        docRef.current?.destroy();
        docRef.current = null;
        isRenderingRef.current.clear();

        const doc = await pdfjsLib.getDocument(pdfUrl).promise;
        if (cancelled) { doc.destroy(); return; }

        docRef.current = doc;
        setTotalPages(doc.numPages);
        setCurrentPage(1);
        await buildPages(doc);
      } catch {
        if (!cancelled) setError('PDF yüklenemedi.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [pdfUrl, buildPages]);

  // Zoom: only update CSS sizes, re-render visible pages
  useEffect(() => {
    zoomRef.current = zoom;
    const zf = zoom / 100;

    // Update placeholder div sizes
    pageDivRefs.current.forEach((div, i) => {
      const vp = pageViewportsRef.current[i - 1];
      if (!vp) return;
      div.style.width = `${vp.width * zf}px`;
      div.style.height = `${vp.height * zf}px`;
    });

    // Update rendered canvas CSS sizes
    pageDivRefs.current.forEach((div) => {
      const canvas = div.querySelector('.pdf-page-canvas') as HTMLCanvasElement | null;
      if (!canvas) return;
      const pageNum = Number(div.dataset.page);
      const vp = pageViewportsRef.current[pageNum - 1];
      if (!vp) return;
      canvas.style.width = `${Math.floor(vp.width * zf)}px`;
      canvas.style.height = `${Math.floor(vp.height * zf)}px`;
    });

    // Re-render visible pages (pixel quality stays crisp)
    isRenderingRef.current.clear();
  }, [zoom]);

  // Scroll tracking
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const vp = pageViewportsRef.current;
      if (vp.length === 0) return;
      const scrollTop = container.scrollTop;
      const viewH = container.clientHeight;
      let acc = 0;
      for (let i = 0; i < vp.length; i++) {
        acc += vp[i].height * (zoomRef.current / 100) + 8;
        if (acc > scrollTop + viewH * 0.3) { setCurrentPage(i + 1); return; }
      }
      setCurrentPage(vp.length);
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Ctrl+Wheel zoom
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setZoom((prev) => {
        const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
        return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev + delta));
      });
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleWheel);
  }, []);

  const handleDownload = useCallback(() => {
    if (!pdfUrl) return;
    const downloadUrl = pdfUrl.replace('/api/pdf?', '/api/pdf?download=true&');
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [pdfUrl]);

  const goToPage = useCallback(
    (page: number) => {
      if (page < 1 || page > totalPages) return;
      const div = pageDivRefs.current.get(page);
      if (div) div.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setCurrentPage(page);
    },
    [totalPages],
  );

  return (
    <div className="pdf-viewer">
      {pdfUrl && (
        <div className="pdf-toolbar">
          <div className="pdf-toolbar-group">
            <button className="pdf-toolbar-btn" onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1} title="Önceki sayfa">&#8249;</button>
            <span className="pdf-page-counter">{currentPage} / {totalPages}</span>
            <button className="pdf-toolbar-btn" onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages} title="Sonraki sayfa">&#8250;</button>
          </div>
          <div className="pdf-toolbar-group">
            <button className="pdf-toolbar-btn" onClick={() => setZoom(z => Math.max(MIN_ZOOM, z - ZOOM_STEP))} disabled={zoom <= MIN_ZOOM} title="Uzaklaş">-</button>
            <span className="pdf-zoom-label">{zoom}%</span>
            <button className="pdf-toolbar-btn" onClick={() => setZoom(z => Math.min(MAX_ZOOM, z + ZOOM_STEP))} disabled={zoom >= MAX_ZOOM} title="Yakınlaş">+</button>
            <button className="pdf-toolbar-btn pdf-download-btn" onClick={handleDownload} title="PDF'i Kaydet">&#x2B13;</button>
          </div>
        </div>
      )}
      <div className="pdf-content" ref={containerRef} tabIndex={0}>
        {!pdfUrl && <div className="pdf-empty">PDF yok</div>}
        {loading && <div className="pdf-loading">PDF yükleniyor...</div>}
        {error && <div className="pdf-error">{error}</div>}
        <div className="pdf-pages" ref={pagesContainerRef} />
      </div>
    </div>
  );
}
