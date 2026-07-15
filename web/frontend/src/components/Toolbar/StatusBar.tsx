import { useMemo } from 'react';
import { useCompileStore } from '../../store/compileStore';
import './StatusBar.css';

interface StatusBarProps {
  lineNumber: number;
  columnNumber: number;
  content?: string;
}

export default function StatusBar({ lineNumber, columnNumber, content = '' }: StatusBarProps) {
  const { status, engine } = useCompileStore();

  const statusText = (() => {
    switch (status) {
      case 'idle':
        return 'Hazır';
      case 'compiling':
        return 'Derleniyor...';
      case 'success':
        return 'Derleme başarılı';
      case 'error':
        return 'Derleme hatası';
      default:
        return '';
    }
  })();

  const wordCount = useMemo(() => {
    if (!content) return { words: 0, chars: 0 };
    return {
      words: content.split(/\s+/).filter(Boolean).length,
      chars: content.length,
    };
  }, [content]);

  const statusClass = `statusbar-status statusbar-status--${status}`;

  return (
    <div className="statusbar">
      <div className="statusbar-section statusbar-section--left">
        <span className={statusClass}>{statusText}</span>
        {status === 'compiling' && <div className="statusbar-progress" />}
      </div>
      <div className="statusbar-section statusbar-section--center">
        <span className="statusbar-engine">{engine}</span>
      </div>
      <div className="statusbar-section statusbar-section--right">
        <span className="statusbar-wordcount">
          {wordCount.words} kelime, {wordCount.chars} karakter
        </span>
        <span className="statusbar-cursor">
          Satır {lineNumber}, Sütun {columnNumber}
        </span>
      </div>
    </div>
  );
}
