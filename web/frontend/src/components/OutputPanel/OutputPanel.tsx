import { useCallback, useEffect, useRef, useState } from 'react';
import type { LatexError, LatexWarning, LatexSuggestion } from '../../types';
import './OutputPanel.css';

interface OutputPanelProps {
  errors: LatexError[];
  warnings: LatexWarning[];
  suggestions: LatexSuggestion[];
  logLines: string[];
  onErrorClick: (file_path: string, line: number) => void;
  onWarningClick?: (file_path: string, line: number) => void;
}

type TabId = 'errors' | 'warnings' | 'suggestions' | 'log';

export default function OutputPanel({
  errors,
  warnings,
  suggestions,
  logLines,
  onErrorClick,
  onWarningClick,
}: OutputPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('log');
  const logContainerRef = useRef<HTMLDivElement>(null);
  const prevLogLengthRef = useRef(0);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; text: string } | null>(null);

  const handleContextMenu = useCallback((e: React.MouseEvent, text: string) => {
    e.preventDefault();
    setCtxMenu({ x: e.clientX, y: e.clientY, text });
  }, []);

  const handleCopy = useCallback(() => {
    if (ctxMenu) {
      navigator.clipboard.writeText(ctxMenu.text);
      setCtxMenu(null);
    }
  }, [ctxMenu]);

  const closeContextMenu = useCallback(() => {
    setCtxMenu(null);
  }, []);

  // Auto-switch to Errors tab if errors exist, Suggestions if only suggestions, Warnings if only warnings
  useEffect(() => {
    if (errors.length > 0) {
      setActiveTab('errors');
    } else if (suggestions.length > 0) {
      setActiveTab('suggestions');
    } else if (warnings.length > 0) {
      setActiveTab('warnings');
    }
  }, [errors.length, warnings.length, suggestions.length]);

  // Auto-scroll log to bottom when new lines appear
  useEffect(() => {
    const el = logContainerRef.current;
    if (!el || activeTab !== 'log') return;

    if (logLines.length > prevLogLengthRef.current) {
      el.scrollTop = el.scrollHeight;
    }
    prevLogLengthRef.current = logLines.length;
  }, [logLines.length, activeTab]);

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: 'errors', label: 'Hatalar', count: errors.length },
    { id: 'suggestions', label: 'Öneriler', count: suggestions.length },
    { id: 'warnings', label: 'Uyarılar', count: warnings.length },
    { id: 'log', label: 'Log' },
  ];

  return (
    <div className="output-panel">
      <div className="output-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`output-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count !== undefined && ` (${tab.count})`}
          </button>
        ))}
      </div>
      <div className="output-content">
        {activeTab === 'errors' && (
          <div className="output-list output-errors-list">
            {errors.length === 0 ? (
              <div className="output-empty">Hata yok</div>
            ) : (
              errors.map((err, idx) => (
                <div
                  key={`${err.file_path}-${err.line_number}-${idx}`}
                  className="output-item output-error-item"
                  onClick={() => onErrorClick(err.file_path, err.line_number)}
                  onContextMenu={(e) => handleContextMenu(e, `Satır ${err.line_number}: ${err.message}`)}
                  title={`${err.file_path}:${err.line_number}`}
                >
                  <span className="output-error-line">
                    Satır {err.line_number}:
                  </span>{' '}
                  <span className="output-error-msg">{err.message}</span>
                </div>
              ))
            )}
          </div>
        )}
        {activeTab === 'warnings' && (
          <div className="output-list output-warnings-list">
            {warnings.length === 0 ? (
              <div className="output-empty">Uyarı yok</div>
            ) : (
              warnings.map((warn, idx) => (
                <div
                  key={`${warn.warning_type}-${warn.line_number}-${idx}`}
                  className="output-item output-warning-item"
                  onClick={() => onWarningClick?.(warn.file_path, warn.line_number)}
                  onContextMenu={(e) => {
                    const parts: string[] = [];
                    if (warn.line_number > 0) parts.push(`Satır ${warn.line_number}:`);
                    if (warn.warning_type) parts.push(`[${warn.warning_type}]`);
                    parts.push(warn.message);
                    handleContextMenu(e, parts.join(' '));
                  }}
                  title={warn.file_path ? `${warn.file_path}:${warn.line_number}` : `Satır ${warn.line_number}`}
                >
                  {warn.line_number > 0 && (
                    <span className="output-warning-line">
                      Satır {warn.line_number}:
                    </span>
                  )}{' '}
                  <span className="output-warning-type">
                    [{warn.warning_type}]
                  </span>{' '}
                  <span className="output-warning-msg">{warn.message}</span>
                </div>
              ))
            )}
          </div>
        )}
        {activeTab === 'suggestions' && (
          <div className="output-list output-suggestions-list">
            {suggestions.length === 0 ? (
              <div className="output-empty">Öneri yok</div>
            ) : (
              suggestions.map((s, idx) => (
                <div
                  key={`suggestion-${idx}`}
                  className="output-item output-suggestion-item"
                  onContextMenu={(e) => {
                    const text = s.install_command
                      ? `${s.message}\n${s.install_command}`
                      : s.message;
                    handleContextMenu(e, text);
                  }}
                >
                  <span className="output-suggestion-msg">{s.message}</span>
                  {s.install_command && (
                    <span className="output-suggestion-cmd">{s.install_command}</span>
                  )}
                </div>
              ))
            )}
          </div>
        )}
        {activeTab === 'log' && (
          <div className="output-log" ref={logContainerRef}>
            {logLines.map((line, idx) => (
              <div key={idx} className="output-log-line">
                {line}
              </div>
            ))}
          </div>
        )}
      </div>
      {ctxMenu && (
        <div className="ctx-overlay" onClick={closeContextMenu} onContextMenu={(e) => { e.preventDefault(); closeContextMenu(); }}>
          <div className="ctx-menu" style={{ top: ctxMenu.y, left: ctxMenu.x }}>
            <button className="ctx-menu-item" onClick={handleCopy}>Kopyala</button>
          </div>
        </div>
      )}
    </div>
  );
}
