export interface FileNode {
  name: string;
  type: 'file' | 'dir';
  path: string;
  children?: FileNode[];
}

export interface InputNode {
  name: string;
  path: string;
  is_dir?: boolean;
  children: InputNode[];
}

export interface Tab {
  path: string;
  name: string;
  isDirty: boolean;
  detectedEngine?: string;
  model?: unknown;
}

export interface LatexError {
  line_number: number;
  message: string;
  file_path: string;
}

export interface LatexWarning {
  line_number: number;
  message: string;
  warning_type: string;
  file_path: string;
}

export interface LatexSuggestion {
  message: string;
  install_command: string;
}

export interface CompileResult {
  success: boolean;
  pdf_path: string;
  errors: LatexError[];
  warnings: LatexWarning[];
  suggestions: LatexSuggestion[];
  raw_output: string;
}

export interface SessionData {
  open_tabs: string[];
  active_tab: number;
  engine: string;
}
