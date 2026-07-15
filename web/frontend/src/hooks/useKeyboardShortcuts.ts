import { useEffect } from 'react';

interface ShortcutHandlers {
  onSave: () => void;
  onCompile: () => void;
  onStop: () => void;
  onOpenFolder?: () => void;
  onCloseTab?: () => void;
}

export function useKeyboardShortcuts({ onSave, onCompile, onStop, onOpenFolder, onCloseTab }: ShortcutHandlers) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 's':
            e.preventDefault();
            onSave();
            break;
          case 'b':
            e.preventDefault();
            onCompile();
            break;
          case 'o':
            e.preventDefault();
            onOpenFolder?.();
            break;
          case 'w':
            e.preventDefault();
            onCloseTab?.();
            break;
        }
      }
      if (e.key === 'Escape') {
        onStop();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onSave, onCompile, onStop, onOpenFolder, onCloseTab]);
}
