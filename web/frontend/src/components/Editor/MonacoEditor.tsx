import { useCallback, useEffect, useRef } from 'react';
import MonacoEditorComponent from '@monaco-editor/react';
import type { editor as MonacoEditorType } from 'monaco-editor';
import { defineAllLatexThemes, monacoThemeName } from './latexTheme';
import { useThemeStore } from '../../store/themeStore';
import { registerLatexLanguage } from './latexLanguage';
import { registerLatexTokenizer } from './latexTokenizer';
import { registerLatexCompletions } from '../../utils/latexCommands';
import './MonacoEditor.css';

export interface MonacoEditorProps {
  value: string;
  path: string;
  onChange?: (value: string) => void;
  onMount?: (editor: MonacoEditorType.IStandaloneCodeEditor) => void;
  onSynctexForward?: (line: number, col: number) => void;
}

const modelsMap = new Map<string, MonacoEditorType.ITextModel>();
let latexRegistered = false;

// Register BEFORE editor creation
function ensureLatexRegistered(monaco: typeof import('monaco-editor')) {
  if (latexRegistered) return;
  registerLatexLanguage(monaco);
  registerLatexTokenizer(monaco);
  defineAllLatexThemes(monaco);
  registerLatexCompletions(monaco);
  latexRegistered = true;
}

export function MonacoEditor({
  value,
  path,
  onChange,
  onMount,
  onSynctexForward,
}: MonacoEditorProps) {
  const editorRef = useRef<MonacoEditorType.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof import('monaco-editor') | null>(null);
  const pathRef = useRef<string>(path);
  const suppressChangeRef = useRef(false);
  // SyncTeX forward callback — ref ile sakla (mount'ta kaydedilen listener güncel kalsın)
  const onForwardRef = useRef(onSynctexForward);
  onForwardRef.current = onSynctexForward;
  const theme = useThemeStore((s) => s.theme);

  const handleBeforeMount = useCallback((monaco: typeof import('monaco-editor')) => {
    ensureLatexRegistered(monaco);
  }, []);

  const handleEditorDidMount = useCallback(
    (editor: MonacoEditorType.IStandaloneCodeEditor, monaco: typeof import('monaco-editor')) => {
      editorRef.current = editor;
      monacoRef.current = monaco;

      // Create or reuse model for the initial path
      const uri = monaco.Uri.parse(`file:///${path}`);
      let model = monaco.editor.getModel(uri);
      if (!model) {
        model = monaco.editor.createModel(value, 'latex', uri);
      } else {
        suppressChangeRef.current = true;
        model.setValue(value);
        suppressChangeRef.current = false;
      }
      modelsMap.set(path, model);
      editor.setModel(model);

      // Ctrl+/ comment toggle
      editor.addAction({
        id: 'latex-comment-toggle',
        label: 'Toggle Comment',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Slash],
        run: (ed) => {
          const selection = ed.getSelection();
          if (!selection) return;
          const mdl = ed.getModel();
          if (!mdl) return;

          const startLine = selection.startLineNumber;
          const endLine = selection.endLineNumber;

          ed.pushUndoStop();

          let allCommented = true;
          for (let i = startLine; i <= endLine; i++) {
            const line = mdl.getLineContent(i).trimStart();
            if (line.length > 0 && !line.startsWith('%')) {
              allCommented = false;
              break;
            }
          }

          for (let i = startLine; i <= endLine; i++) {
            const line = mdl.getLineContent(i);
            if (allCommented) {
              const trimmed = line.trimStart();
              if (trimmed.startsWith('%')) {
                const indent = line.length - line.trimStart().length;
                const newLine = line.substring(0, indent) + trimmed.substring(1);
                mdl.applyEdits([{
                  range: new monaco.Range(i, 1, i, line.length + 1),
                  text: newLine,
                }]);
              }
            } else {
              const indent = line.length - line.trimStart().length;
              const newLine = line.substring(0, indent) + '% ' + line.substring(indent);
              mdl.applyEdits([{
                range: new monaco.Range(i, 1, i, line.length + 1),
                text: newLine,
              }]);
            }
          }

          ed.pushUndoStop();
        },
      });

      // Ctrl/Cmd+click → SyncTeX forward arama (editör satırı → PDF)
      editor.onMouseDown((e) => {
        const pos = e.target?.position;
        if ((e.event.ctrlKey || e.event.metaKey) && pos) {
          e.event.preventDefault();
          onForwardRef.current?.(pos.lineNumber, pos.column);
        }
      });

      pathRef.current = path;
      onMount?.(editor);
    },
    [onMount, path, value],
  );

  // Switch model when path changes
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    if (path === pathRef.current) return;

    const uri = monaco.Uri.parse(`file:///${path}`);
    let model = monaco.editor.getModel(uri);
    if (!model) {
      model = monaco.editor.createModel(value, 'latex', uri);
    }
    modelsMap.set(path, model);
    editor.setModel(model);
    pathRef.current = path;
  }, [path, value]);

  // Sync external value changes
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const model = editor.getModel();
    if (!model) return;
    const currentValue = model.getValue();
    if (currentValue !== value) {
      suppressChangeRef.current = true;
      const position = editor.getPosition();
      model.setValue(value);
      if (position) editor.setPosition(position);
      suppressChangeRef.current = false;
    }
  }, [value]);

  const handleChange = useCallback(
    (newValue: string | undefined) => {
      if (suppressChangeRef.current) return;
      onChange?.(newValue ?? '');
    },
    [onChange],
  );

  return (
    <div className="monaco-editor-wrapper">
      <MonacoEditorComponent
        height="100%"
        language="latex"
        theme={monacoThemeName(theme)}
        beforeMount={handleBeforeMount}
        onChange={handleChange}
        onMount={handleEditorDidMount}
        options={{
          wordWrap: 'on',
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          renderWhitespace: 'selection',
          bracketPairColorization: { enabled: false },
          padding: { top: 8 },
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          fixedOverflowWidgets: true,
          quickSuggestions: true,
          suggestOnTriggerCharacters: true,
          parameterHints: { enabled: false },
          folding: true,
          foldingStrategy: 'indentation',
          renderLineHighlight: 'line',
          contextmenu: true,
        }}
        loading={<div className="monaco-editor-loading">Loading editor...</div>}
      />
    </div>
  );
}
