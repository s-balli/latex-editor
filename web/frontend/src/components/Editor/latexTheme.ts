import type * as Monaco from 'monaco-editor';

export const THEME_NAME = 'latex-dark';

export function defineLatexTheme(monaco: typeof Monaco): void {
  monaco.editor.defineTheme(THEME_NAME, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      // Default text — white
      { token: '', foreground: 'd4d4d4' },

      // Commands: \section, \begin — blue (#569cd6)
      { token: 'keyword', foreground: '569cd6' },

      // Comments: % ... — green italic (#6a9955)
      { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },

      // Brace args: {content} — orange (#ce9178)
      { token: 'string', foreground: 'ce9178' },

      // {} delimiters — white
      { token: 'delimiter.bracket', foreground: 'd4d4d4' },

      // [] delimiters and content — green (#b5cea8)
      { token: 'delimiter.square', foreground: 'b5cea8' },
      { token: 'number', foreground: 'b5cea8' },

      // Math: $content$ — purple (#c586c0)
      { token: 'regexp', foreground: 'c586c0' },

      // Math commands: \alpha inside $ — light blue (#9cdcfe)
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
  });
}
