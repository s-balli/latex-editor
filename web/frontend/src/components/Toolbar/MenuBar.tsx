import { useState, useRef, useEffect, useCallback } from 'react';
import { useCompileStore } from '../../store/compileStore';
import './MenuBar.css';

interface MenuBarProps {
  onOpenFolder: () => void;
  onSave: () => void;
  onCompile: () => void;
  onStop: () => void;
}

interface MenuItem {
  label: string;
  shortcut?: string;
  action?: () => void;
  separator?: boolean;
}

export default function MenuBar({ onOpenFolder, onSave, onCompile, onStop }: MenuBarProps) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const compiling = useCompileStore(s => s.status === 'compiling');

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setOpenMenu(null);
    }
  }, []);

  useEffect(() => {
    if (openMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [openMenu, handleClickOutside]);

  const menus: Record<string, MenuItem[]> = {
    'Dosya': [
      { label: 'Klasör Aç', shortcut: 'Ctrl+O', action: () => { onOpenFolder(); setOpenMenu(null); } },
      { label: 'Kaydet', shortcut: 'Ctrl+S', action: () => { onSave(); setOpenMenu(null); } },
      { separator: true, label: '' },
      { label: 'Kapat', shortcut: 'Ctrl+W', action: () => { setOpenMenu(null); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', ctrlKey: true })); } },
    ],
    'Düzenle': [
      { label: 'Geri Al', shortcut: 'Ctrl+Z', action: () => { setOpenMenu(null); document.execCommand('undo'); } },
      { label: 'Yinele', shortcut: 'Ctrl+Y', action: () => { setOpenMenu(null); document.execCommand('redo'); } },
      { separator: true, label: '' },
      { label: 'Bul', shortcut: 'Ctrl+F', action: () => { setOpenMenu(null); } },
      { label: 'Bul ve Değiştir', shortcut: 'Ctrl+H', action: () => { setOpenMenu(null); } },
      { separator: true, label: '' },
      { label: 'Yorum Toggle', shortcut: 'Ctrl+/', action: () => { setOpenMenu(null); } },
      { label: 'Satıra Git', shortcut: 'Ctrl+G', action: () => { setOpenMenu(null); } },
    ],
    'Derle': [
      { label: compiling ? 'Durdur' : 'Derle', shortcut: 'Ctrl+B', action: () => { compiling ? onStop() : onCompile(); setOpenMenu(null); } },
    ],
    'Yardım': [
      { label: 'Klavye Kısayolları', action: () => { setOpenMenu(null); showShortcutsDialog(); } },
    ],
  };

  return (
    <div className="menubar" ref={menuRef}>
      {Object.entries(menus).map(([name, items]) => (
        <div key={name} className="menubar-item">
          <button
            className={`menubar-trigger ${openMenu === name ? 'menubar-trigger--open' : ''}`}
            onClick={() => setOpenMenu(openMenu === name ? null : name)}
            onMouseEnter={() => openMenu && setOpenMenu(name)}
          >
            {name}
          </button>
          {openMenu === name && (
            <div className="menubar-dropdown">
              {items.map((item, idx) =>
                item.separator ? (
                  <div key={idx} className="menubar-separator" />
                ) : (
                  <button
                    key={idx}
                    className="menubar-dropdown-item"
                    onClick={item.action}
                  >
                    <span>{item.label}</span>
                    {item.shortcut && <span className="menubar-shortcut">{item.shortcut}</span>}
                  </button>
                )
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function showShortcutsDialog() {
  const shortcuts = [
    ['Ctrl+S', 'Kaydet + Otomatik Derle'],
    ['Ctrl+B', 'Derle'],
    ['Ctrl+O', 'Klasör Aç'],
    ['Ctrl+W', 'Sekmeyi Kapat'],
    ['Ctrl+Z', 'Geri Al'],
    ['Ctrl+Y', 'Yinele'],
    ['Ctrl+F', 'Bul'],
    ['Ctrl+H', 'Bul ve Değiştir'],
    ['Ctrl+/', 'Yorum Toggle'],
    ['Ctrl+G', 'Satıra Git'],
    ['Esc', 'Derlemeyi Durdur'],
  ];

  const rows = shortcuts.map(([key, desc]) =>
    `<tr><td class="sc-key"><kbd>${key}</kbd></td><td class="sc-desc">${desc}</td></tr>`
  ).join('');

  const overlay = document.createElement('div');
  overlay.className = 'shortcuts-overlay';
  overlay.innerHTML = `
    <div class="shortcuts-dialog">
      <div class="shortcuts-title">Klavye Kısayolları</div>
      <table class="shortcuts-table">${rows}</table>
      <div class="shortcuts-footer">
        <button class="shortcuts-close">Kapat</button>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    .shortcuts-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.5);
      display: flex; align-items: center; justify-content: center; z-index: 10000;
    }
    .shortcuts-dialog {
      background: #2d2d2d; border: 1px solid #454545; border-radius: 8px;
      padding: 20px 24px; min-width: 360px; max-width: 480px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #ccc; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    }
    .shortcuts-title {
      font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #e0e0e0;
      border-bottom: 1px solid #444; padding-bottom: 10px;
    }
    .shortcuts-table { width: 100%; border-collapse: collapse; }
    .shortcuts-table td { padding: 6px 0; }
    .sc-key { width: 120px; }
    .sc-key kbd {
      background: #3c3c3c; padding: 3px 8px; border-radius: 4px;
      font-family: 'Consolas', 'Menlo', monospace; font-size: 12px;
      border: 1px solid #555; color: #e0e0e0;
    }
    .sc-desc { color: #aaa; font-size: 13px; }
    .shortcuts-footer { margin-top: 16px; text-align: right; border-top: 1px solid #444; padding-top: 12px; }
    .shortcuts-close {
      background: #3a6ea5; color: #fff; border: none; padding: 6px 20px;
      border-radius: 4px; cursor: pointer; font-size: 13px;
    }
    .shortcuts-close:hover { background: #4a8ec5; }
  `;

  document.head.appendChild(style);
  document.body.appendChild(overlay);

  const close = () => { overlay.remove(); style.remove(); };
  overlay.querySelector('.shortcuts-close')!.addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
}
