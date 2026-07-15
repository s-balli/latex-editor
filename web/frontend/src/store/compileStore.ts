import { create } from 'zustand';
import type { CompileResult } from '../types';

interface CompileState {
  status: 'idle' | 'compiling' | 'success' | 'error';
  engine: 'lualatex' | 'pdflatex';
  autoCompile: boolean;
  result: CompileResult | null;
  outputLines: string[];
  compileId: string | null;
  setStatus: (status: CompileState['status']) => void;
  setEngine: (engine: CompileState['engine']) => void;
  toggleAutoCompile: () => void;
  setResult: (result: CompileResult) => void;
  addOutputLine: (line: string) => void;
  clearOutput: () => void;
  setCompileId: (id: string | null) => void;
}

export const useCompileStore = create<CompileState>((set) => ({
  status: 'idle',
  engine: 'lualatex',
  autoCompile: true,
  result: null,
  outputLines: [],
  compileId: null,

  setStatus: (status) => set({ status }),
  setEngine: (engine) => set({ engine }),
  toggleAutoCompile: () => set(state => ({ autoCompile: !state.autoCompile })),
  setResult: (result) => set({ result, status: result.success ? 'success' : 'error' }),
  addOutputLine: (line) => set(state => ({ outputLines: [...state.outputLines, line] })),
  clearOutput: () => set({ outputLines: [], result: null }),
  setCompileId: (id) => set({ compileId: id }),
}));
