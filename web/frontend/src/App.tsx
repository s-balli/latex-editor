import { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';

import { useEditorStore } from './store/editorStore';
import { useCompileStore } from './store/compileStore';
import { useCompile } from './hooks/useCompile';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { listFiles, readFile, writeFile, detectEngine } from './api/files';
import { getPdfUrl } from './api/compile';
import { forwardSearch, reverseSearch, type ForwardResult } from './api/synctex';
import { apiFetch } from './api/client';

import Toolbar from './components/Toolbar/Toolbar';
import MenuBar from './components/Toolbar/MenuBar';
import StatusBar from './components/Toolbar/StatusBar';
import MainLayout from './components/Layout/MainLayout';
import FileTree from './components/FileTree/FileTree';
import EditorTabs from './components/Editor/EditorTabs';
import { MonacoEditor } from './components/Editor/MonacoEditor';
import PdfViewer from './components/PdfViewer/PdfViewer';
import OutputPanel from './components/OutputPanel/OutputPanel';

import type { FileNode } from './types';

function App() {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [cursorLine, setCursorLine] = useState(1);
  const [cursorCol, setCursorCol] = useState(1);
  const [appVersion, setAppVersion] = useState('');
  const [synctexTarget, setSynctexTarget] = useState<(ForwardResult & { nonce: number }) | null>(null);
  const editorRef = useRef<any>(null);

  const {
    tabs, activeTab, openTab, closeTab, setActiveTab,
    markDirty, setTabContent, tabContents, setDetectedEngine,
    saveSession, loadSession,
  } = useEditorStore();
  const { result, outputLines } = useCompileStore();
  const { compile, stop, saveAndCompile } = useCompile();

  // Versiyonu çek
  useEffect(() => {
    apiFetch('/version').then((data: any) => setAppVersion(data.version)).catch(() => {});
  }, []);

  // Klasör aç
  const handleOpenFolder = useCallback(async () => {
    const path = prompt('Proje klasör yolunu girin (örn: /home/user/proje):');
    if (path) {
      const result = await listFiles(path);
      setFiles(result);
    }
  }, []);

  // Dosya aç + motor algıla
  const handleFileClick = useCallback(async (path: string) => {
    try {
      const isNew = !tabs.find(t => t.path === path);
      if (isNew) {
        const { content } = await readFile(path);
        setTabContent(path, content);
      }
      openTab(path);
      if (isNew) {
        try {
          const { engine } = await detectEngine(path);
          setDetectedEngine(path, engine);
          useCompileStore.getState().setEngine(engine as 'lualatex' | 'pdflatex');
        } catch { /* algılama başarısız — mevcut motor korunur */ }
      }
    } catch (err) {
      console.error('[App] handleFileClick error:', err);
    }
  }, [tabs, openTab, setTabContent, setDetectedEngine]);

  // Tab değişince motoru restore et
  useEffect(() => {
    if (!activeTab) return;
    const currentTabs = useEditorStore.getState().tabs;
    const tab = currentTabs.find(t => t.path === activeTab);
    if (tab?.detectedEngine) {
      useCompileStore.getState().setEngine(tab.detectedEngine as 'lualatex' | 'pdflatex');
    }
  }, [activeTab]);

  // Tab değişince content yükle
  const activeContent = activeTab ? tabContents[activeTab] || '' : '';

  // Editor değişiklik
  const handleChange = useCallback((value: string | undefined) => {
    if (activeTab && value !== undefined) {
      setTabContent(activeTab, value);
      markDirty(activeTab, true);
    }
  }, [activeTab, setTabContent, markDirty]);

  // Editor mount
  const handleEditorMount = useCallback((editor: any) => {
    editorRef.current = editor;
    editor.onDidChangeCursorPosition((e: any) => {
      setCursorLine(e.position.lineNumber);
      setCursorCol(e.position.column);
    });
  }, []);

  // Derleme sonrası PDF güncelle (cache busting ile)
  useEffect(() => {
    if (result?.pdf_path) {
      setPdfUrl(getPdfUrl(result.pdf_path) + '&t=' + Date.now());
    }
  }, [result]);

  // Hata/uyarı tıklama — async navigasyon
  // Dosya + satıra git (hata tıklama ve SyncTeX reverse ortak mantığı)
  const gotoFileLine = useCallback(async (filePath: string, line: number) => {
    // Mutlak yol → mevcut tab'la eşleştir (tab'lar göreceli yol tutuyor)
    const existingTab = filePath
      ? tabs.find(t => t.path === filePath || filePath.endsWith('/' + t.path) || filePath.endsWith(t.path))
      : null;
    if (existingTab) {
      setActiveTab(existingTab.path);
    } else if (filePath) {
      await handleFileClick(filePath);
    }
    // Editor'ün yeni model'i yüklemesi için bir tick bekle
    requestAnimationFrame(() => {
      if (editorRef.current && line > 0) {
        editorRef.current.revealLineInCenter(line);
        editorRef.current.setPosition({ lineNumber: line, column: 1 });
        editorRef.current.focus();
      }
    });
  }, [handleFileClick, tabs, setActiveTab]);

  const handleErrorClick = useCallback(async (filePath: string, line: number) => {
    await gotoFileLine(filePath, line);
  }, [gotoFileLine]);

  // SyncTeX forward: editör Ctrl/Cmd+click → PDF konumu
  const handleForwardSearch = useCallback(async (line: number, col: number) => {
    const pdfPath = result?.pdf_path;
    if (!pdfPath || !activeTab) return;
    try {
      const r = await forwardSearch(activeTab, line, col, pdfPath);
      setSynctexTarget({ ...r, nonce: Date.now() });
    } catch (err) {
      console.warn('[SyncTeX] forward başarısız:', err);
    }
  }, [result, activeTab]);

  // SyncTeX reverse: PDF Ctrl/Cmd+click → kaynak dosya + satır
  const handleReverseSearch = useCallback(async (page: number, x: number, y: number) => {
    const pdfPath = result?.pdf_path;
    if (!pdfPath) return;
    try {
      const r = await reverseSearch(page, x, y, pdfPath);
      await gotoFileLine(r.file_path, r.line);
    } catch (err) {
      console.warn('[SyncTeX] reverse başarısız:', err);
    }
  }, [result, gotoFileLine]);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onSave: saveAndCompile,
    onCompile: () => compile(),
    onStop: stop,
    onOpenFolder: handleOpenFolder,
    onCloseTab: () => {
      if (activeTab) {
        const tab = tabs.find(t => t.path === activeTab);
        if (tab?.isDirty) {
          const ok = window.confirm(`'${tab.name}' dosyasında kaydedilmemiş değişiklikler var.\n\nTamam = Kaydet ve Kapat\nİptal = Kapatma`);
          if (!ok) return;
          const content = tabContents[activeTab];
          if (content !== undefined) {
            writeFile(activeTab, content);
            markDirty(activeTab, false);
          }
        }
        closeTab(activeTab);
      }
    },
  });

  // Sekme kapatma (dirty uyarı ile)
  const handleCloseTab = useCallback(async (path: string) => {
    const tab = tabs.find(t => t.path === path);
    if (tab?.isDirty) {
      const ok = window.confirm(`'${tab.name}' dosyasında kaydedilmemiş değişiklikler var.\n\nTamam = Kaydet ve Kapat\nİptal = Kapatma`);
      if (!ok) return;
      const content = tabContents[path];
      if (content !== undefined) {
        await writeFile(path, content);
        markDirty(path, false);
      }
    }
    closeTab(path);
  }, [tabs, tabContents, closeTab, markDirty]);

  // Session: mount'ta yükle
  useEffect(() => {
    (async () => {
      const session = loadSession();
      for (const path of session.tabs) {
        try {
          const { content } = await readFile(path);
          setTabContent(path, content);
          try {
            const { engine } = await detectEngine(path);
            setDetectedEngine(path, engine);
          } catch { /* algılama başarısız — yoksay */ }
          openTab(path);
        } catch { /* dosya artık yoksa atla */ }
      }
      if (session.activeTab) {
        setActiveTab(session.activeTab);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Session: değişikliklerde kaydet
  useEffect(() => {
    if (tabs.length > 0) saveSession();
  }, [tabs, activeTab, saveSession]);

  // Beforeunload: dirty uyarı + son session kaydet
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      saveSession();
      if (tabs.some(t => t.isDirty)) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [tabs, saveSession]);

  return (
    <div className="app">
      <MenuBar
        onOpenFolder={handleOpenFolder}
        onSave={saveAndCompile}
        onCompile={() => compile()}
        onStop={stop}
      />
      <Toolbar
        onOpenFolder={handleOpenFolder}
        onSave={saveAndCompile}
        onCompile={() => compile()}
        onStop={stop}
      />
      <MainLayout
        fileTree={
          <FileTree files={files} onFileClick={handleFileClick} activeFilePath={activeTab ?? undefined} />
        }
        editor={
          <div className="editor-area">
            <EditorTabs
              tabs={tabs}
              activeTab={activeTab}
              onTabClick={setActiveTab}
              onTabClose={handleCloseTab}
            />
            {activeTab ? (
              <MonacoEditor
                value={activeContent}
                path={activeTab}
                onChange={handleChange}
                onMount={handleEditorMount}
                onSynctexForward={handleForwardSearch}
              />
            ) : (
              <div className="empty-editor">
                LaTeX Editor Web v{appVersion || '...'}
              </div>
            )}
          </div>
        }
        pdfViewer={<PdfViewer pdfUrl={pdfUrl} synctexTarget={synctexTarget} onReverseSearch={handleReverseSearch} />}
        outputPanel={
          <OutputPanel
            errors={result?.errors || []}
            warnings={result?.warnings || []}
            suggestions={result?.suggestions || []}
            logLines={outputLines}
            onErrorClick={handleErrorClick}
            onWarningClick={handleErrorClick}
          />
        }
      />
      <StatusBar lineNumber={cursorLine} columnNumber={cursorCol} content={activeContent} />
    </div>
  );
}

export default App;
