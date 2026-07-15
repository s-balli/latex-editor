import type * as Monaco from 'monaco-editor';

export function registerLatexLanguage(monaco: typeof Monaco): void {
  monaco.languages.register({ id: 'latex', extensions: ['.tex', '.sty', '.cls', '.bib'] });

  monaco.languages.setLanguageConfiguration('latex', {
    comments: {
      lineComment: '%',
    },
    brackets: [
      ['{', '}'],
      ['[', ']'],
      ['(', ')'],
    ],
    autoClosingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '$', close: '$', notIn: ['comment', 'math'] },
      { open: '`', close: "'" },
      { open: '``', close: "''" },
    ],
    surroundingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '$', close: '$' },
    ],
  });
}
