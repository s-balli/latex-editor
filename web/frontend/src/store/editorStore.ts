import { create } from 'zustand';
import type { Tab } from '../types';

const STORAGE_KEY = 'latex-editor-session';

interface EditorState {
  tabs: Tab[];
  activeTab: string | null;
  tabContents: Record<string, string>;
  openTab: (path: string) => void;
  closeTab: (path: string) => void;
  setActiveTab: (path: string) => void;
  markDirty: (path: string, dirty: boolean) => void;
  setTabContent: (path: string, content: string) => void;
  setDetectedEngine: (path: string, engine: string) => void;
  getDetectedEngine: (path: string) => string | undefined;
  saveSession: () => void;
  loadSession: () => { tabs: string[]; activeTab: string | null; engines: Record<string, string> };
}

export const useEditorStore = create<EditorState>((set, get) => ({
  tabs: [],
  activeTab: null,
  tabContents: {},

  openTab: (path) => {
    const { tabs } = get();
    const name = path.split('/').pop() || path;
    if (!tabs.find(t => t.path === path)) {
      set({ tabs: [...tabs, { path, name, isDirty: false }] });
    }
    set({ activeTab: path });
  },

  closeTab: (path) => {
    const { tabs, activeTab } = get();
    const idx = tabs.findIndex(t => t.path === path);
    const newTabs = tabs.filter(t => t.path !== path);
    let newActive = activeTab;
    if (activeTab === path) {
      newActive = newTabs[Math.min(idx, newTabs.length - 1)]?.path || null;
    }
    set({ tabs: newTabs, activeTab: newActive });
  },

  setActiveTab: (path) => set({ activeTab: path }),

  markDirty: (path, dirty) => {
    set(state => ({
      tabs: state.tabs.map(t => t.path === path ? { ...t, isDirty: dirty } : t),
    }));
  },

  setTabContent: (path, content) => {
    set(state => ({
      tabContents: { ...state.tabContents, [path]: content },
    }));
  },

  setDetectedEngine: (path, engine) => {
    set(state => ({
      tabs: state.tabs.map(t => t.path === path ? { ...t, detectedEngine: engine } : t),
    }));
  },

  getDetectedEngine: (path) => {
    const tab = get().tabs.find(t => t.path === path);
    return tab?.detectedEngine;
  },

  saveSession: () => {
    const { tabs, activeTab } = get();
    const engines: Record<string, string> = {};
    tabs.forEach(t => {
      if (t.detectedEngine) engines[t.path] = t.detectedEngine;
    });
    const data = {
      openTabs: tabs.map(t => t.path),
      activeTab,
      engines,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch { /* ignore */ }
  },

  loadSession: () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { tabs: [], activeTab: null, engines: {} };
      const data = JSON.parse(raw);
      return {
        tabs: data.openTabs || [],
        activeTab: data.activeTab || null,
        engines: data.engines || {},
      };
    } catch {
      return { tabs: [], activeTab: null, engines: {} };
    }
  },
}));
