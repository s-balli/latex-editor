import type * as Monaco from 'monaco-editor';

export function registerLatexTokenizer(monaco: typeof Monaco): void {
  monaco.languages.setMonarchTokensProvider('latex', {
    defaultToken: '',
    tokenPostfix: '',

    tokenizer: {
      root: [
        // Comments
        { regex: /%.*/, action: { token: 'comment' } },

        // Display math $$ (before $)
        { regex: /\$\$/, action: { token: 'regexp', next: '@math_display' } },

        // Inline math $
        { regex: /\$/, action: { token: 'regexp', next: '@math_inline' } },

        // Commands: \word
        { regex: /\\[a-zA-Z@]+\*?/, action: { token: 'keyword' } },

        // Control symbols: \\, \#, etc.
        { regex: /\\./, action: { token: 'keyword' } },

        // { → enter brace arg state (orange content)
        { regex: /\{/, action: { token: 'delimiter.bracket', next: '@brace_arg' } },
        { regex: /\}/, action: { token: 'delimiter.bracket' } },

        // [ → enter bracket arg state (green content)
        { regex: /\[/, action: { token: 'delimiter.square', next: '@bracket_arg' } },
        { regex: /\]/, action: { token: 'delimiter.square' } },
      ],

      // Content inside { }
      brace_arg: [
        { regex: /%.*/, action: { token: 'comment' } },
        { regex: /\$\$/, action: { token: 'regexp', next: '@math_display' } },
        { regex: /\$/, action: { token: 'regexp', next: '@math_inline' } },
        { regex: /\\[a-zA-Z@]+\*?/, action: { token: 'keyword' } },
        { regex: /\\./, action: { token: 'keyword' } },
        { regex: /\{/, action: { token: 'delimiter.bracket', next: '@push' } },
        { regex: /\}/, action: { token: 'delimiter.bracket', next: '@pop' } },
        // Text content → orange
        { regex: /[^\\{}$%]+/, action: { token: 'string' } },
      ],

      // Content inside [ ]
      bracket_arg: [
        { regex: /%.*/, action: { token: 'comment' } },
        { regex: /\\[a-zA-Z@]+\*?/, action: { token: 'keyword' } },
        { regex: /\\./, action: { token: 'keyword' } },
        { regex: /\[/, action: { token: 'delimiter.square', next: '@push' } },
        { regex: /\]/, action: { token: 'delimiter.square', next: '@pop' } },
        // Text content → green
        { regex: /[^\]\\%]+/, action: { token: 'number' } },
      ],

      // Inline math $...$
      math_inline: [
        { regex: /\\[a-zA-Z@]+/, action: { token: 'variable' } },
        { regex: /\\./, action: { token: 'variable' } },
        { regex: /\$\$/, action: { token: 'regexp', next: '@pop' } },
        { regex: /\$/, action: { token: 'regexp', next: '@pop' } },
        // Math text → purple
        { regex: /[^$\\]+/, action: { token: 'regexp' } },
      ],

      // Display math $$...$$
      math_display: [
        { regex: /\\[a-zA-Z@]+/, action: { token: 'variable' } },
        { regex: /\\./, action: { token: 'variable' } },
        { regex: /\$\$/, action: { token: 'regexp', next: '@pop' } },
        // Math text → purple
        { regex: /[^$\\]+/, action: { token: 'regexp' } },
      ],
    },
  });
}
