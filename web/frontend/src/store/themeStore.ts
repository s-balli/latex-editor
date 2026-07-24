import { create } from 'zustand';
import type { ThemeId } from '../components/Editor/latexTheme';

export type { ThemeId };

const STORAGE_KEY = 'latex-editor-theme';

export const THEME_OPTIONS: { id: ThemeId; label: string }[] = [
  { id: 'dark', label: 'Koyu' },
  { id: 'light', label: 'Açık' },
  { id: 'solarized', label: 'Solarized' },
  { id: 'dracula', label: 'Dracula' },
  { id: 'monokai', label: 'Monokai' },
  { id: 'nord', label: 'Nord' },
  { id: 'gruvbox', label: 'Gruvbox' },
];

function loadTheme(): ThemeId {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'dark' || v === 'light' || v === 'solarized' || v === 'dracula' || v === 'monokai' || v === 'nord' || v === 'gruvbox') return v;
  } catch {
    /* ignore */
  }
  return 'dark';
}

interface ThemeState {
  theme: ThemeId;
  setTheme: (t: ThemeId) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: loadTheme(),
  setTheme: (t) => {
    try {
      localStorage.setItem(STORAGE_KEY, t);
    } catch {
      /* ignore */
    }
    set({ theme: t });
  },
}));
