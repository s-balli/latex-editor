import type * as Monaco from 'monaco-editor';

export type ThemeId = 'dark' | 'light' | 'dracula' | 'gruvbox';

interface ThemeDef {
  monacoName: string;
  base: 'vs' | 'vs-dark';
  rules: Monaco.editor.ITokenThemeRule[];
  colors: Record<string, string>;
}

const DARK: ThemeDef = {
  monacoName: 'latex-dark',
  base: 'vs-dark',
  rules: [
    { token: '', foreground: 'd4d4d4' },
    { token: 'keyword', foreground: '569cd6' },
    { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },
    { token: 'string', foreground: 'ce9178' },
    { token: 'delimiter.bracket', foreground: 'd4d4d4' },
    { token: 'delimiter.square', foreground: 'b5cea8' },
    { token: 'number', foreground: 'b5cea8' },
    { token: 'regexp', foreground: 'c586c0' },
    { token: 'variable', foreground: '9cdcfe' },
  ],
  colors: {
    'editor.background': '#1e1e1e',
    'editor.foreground': '#d4d4d4',
    'editor.lineHighlightBackground': '#2a2a2a',
    'editor.selectionBackground': '#264f78',
    'editorCursor.foreground': '#d4d4d4',
    'editorLineNumber.foreground': '#858585',
    'editorLineNumber.activeForeground': '#c6c6c6',
    'editorIndentGuide.background': '#404040',
    'editorBracketMatch.border': '#888888',
    'editorGutter.background': '#1e1e1e',
    'editorHoverWidget.background': '#252526',
    'editorHoverWidget.border': '#454545',
    'editorSuggestWidget.background': '#252526',
    'editorSuggestWidget.border': '#454545',
    'editorSuggestWidget.selectedBackground': '#062f4a',
    'scrollbarSlider.background': '#79797966',
    'scrollbarSlider.hoverBackground': '#646464b3',
  },
};

const LIGHT: ThemeDef = {
  monacoName: 'latex-light',
  base: 'vs',
  rules: [
    { token: '', foreground: '333333' },
    { token: 'keyword', foreground: '0000ff' },
    { token: 'comment', foreground: '008000', fontStyle: 'italic' },
    { token: 'string', foreground: 'a31515' },
    { token: 'delimiter.bracket', foreground: '333333' },
    { token: 'delimiter.square', foreground: '098658' },
    { token: 'number', foreground: '098658' },
    { token: 'regexp', foreground: 'ab47bc' },
    { token: 'variable', foreground: '001080' },
  ],
  colors: {
    'editor.background': '#ffffff',
    'editor.foreground': '#333333',
    'editor.lineHighlightBackground': '#f0f0f0',
    'editor.selectionBackground': '#add6ff',
    'editorCursor.foreground': '#333333',
    'editorLineNumber.foreground': '#b0b0b0',
    'editorLineNumber.activeForeground': '#333333',
    'editorIndentGuide.background': '#e0e0e0',
    'editorBracketMatch.border': '#b0b0b0',
    'editorGutter.background': '#ffffff',
    'editorHoverWidget.background': '#f8f8f8',
    'editorHoverWidget.border': '#d0d0d0',
    'editorSuggestWidget.background': '#f8f8f8',
    'editorSuggestWidget.border': '#d0d0d0',
    'editorSuggestWidget.selectedBackground': '#e0eaff',
    'scrollbarSlider.background': '#64646466',
    'scrollbarSlider.hoverBackground': '#646464b3',
  },
};

const DRACULA: ThemeDef = {
  monacoName: 'latex-dracula',
  base: 'vs-dark',
  rules: [
    { token: '', foreground: 'f8f8f2' },
    { token: 'keyword', foreground: 'ff79c6' },
    { token: 'comment', foreground: '6272a4', fontStyle: 'italic' },
    { token: 'string', foreground: 'f1fa8c' },
    { token: 'delimiter.bracket', foreground: 'f8f8f2' },
    { token: 'delimiter.square', foreground: 'bd93f9' },
    { token: 'number', foreground: 'bd93f9' },
    { token: 'regexp', foreground: 'ff79c6' },
    { token: 'variable', foreground: '50fa7b' },
  ],
  colors: {
    'editor.background': '#282a36',
    'editor.foreground': '#f8f8f2',
    'editor.lineHighlightBackground': '#44475a',
    'editor.selectionBackground': '#44475a',
    'editorCursor.foreground': '#f8f8f2',
    'editorLineNumber.foreground': '#6272a4',
    'editorLineNumber.activeForeground': '#f8f8f2',
    'editorIndentGuide.background': '#44475a',
    'editorBracketMatch.border': '#bd93f9',
    'editorGutter.background': '#282a36',
    'editorHoverWidget.background': '#343746',
    'editorHoverWidget.border': '#44475a',
    'editorSuggestWidget.background': '#343746',
    'editorSuggestWidget.border': '#44475a',
    'editorSuggestWidget.selectedBackground': '#44475a',
    'scrollbarSlider.background': '#6272a466',
    'scrollbarSlider.hoverBackground': '#6272a4b3',
  },
};

const GRUVBOX: ThemeDef = {
  monacoName: 'latex-gruvbox',
  base: 'vs-dark',
  rules: [
    { token: '', foreground: 'ebdbb2' },
    { token: 'keyword', foreground: 'fe8019' },
    { token: 'comment', foreground: '928374', fontStyle: 'italic' },
    { token: 'string', foreground: 'b8bb26' },
    { token: 'delimiter.bracket', foreground: 'ebdbb2' },
    { token: 'delimiter.square', foreground: 'd3869b' },
    { token: 'number', foreground: 'd3869b' },
    { token: 'regexp', foreground: 'fb4934' },
    { token: 'variable', foreground: '83a598' },
  ],
  colors: {
    'editor.background': '#282828',
    'editor.foreground': '#ebdbb2',
    'editor.lineHighlightBackground': '#3c3836',
    'editor.selectionBackground': '#665c54',
    'editorCursor.foreground': '#ebdbb2',
    'editorLineNumber.foreground': '#928374',
    'editorLineNumber.activeForeground': '#ebdbb2',
    'editorIndentGuide.background': '#504945',
    'editorBracketMatch.border': '#fabd2f',
    'editorGutter.background': '#282828',
    'editorHoverWidget.background': '#3c3836',
    'editorHoverWidget.border': '#504945',
    'editorSuggestWidget.background': '#3c3836',
    'editorSuggestWidget.border': '#504945',
    'editorSuggestWidget.selectedBackground': '#504945',
    'scrollbarSlider.background': '#92837466',
    'scrollbarSlider.hoverBackground': '#928374b3',
  },
};

const THEMES: Record<ThemeId, ThemeDef> = { dark: DARK, light: LIGHT, dracula: DRACULA, gruvbox: GRUVBOX };

/** Tüm temaları monaco'ya kaydet (beforeMount'ta çağrılır). */
export function defineAllLatexThemes(monaco: typeof Monaco): void {
  (Object.keys(THEMES) as ThemeId[]).forEach((id) => {
    const t = THEMES[id];
    monaco.editor.defineTheme(t.monacoName, { base: t.base, inherit: true, rules: t.rules, colors: t.colors });
  });
}

/** Tema id → monaco tema adı. */
export function monacoThemeName(id: ThemeId): string {
  return THEMES[id].monacoName;
}
