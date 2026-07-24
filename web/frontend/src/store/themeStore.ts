import { create } from 'zustand';
import type { ThemeId } from '../components/Editor/latexTheme';

export type { ThemeId };

const STORAGE_KEY = 'latex-editor-theme';

export const THEME_OPTIONS: { id: ThemeId; label: string }[] = [
  { id: 'dark', label: 'Koyu' },
  { id: 'light', label: 'Açık' },
  { id: 'dracula', label: 'Dracula' },
];

function loadTheme(): ThemeId {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'dark' || v === 'light' || v === 'dracula') return v;
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
