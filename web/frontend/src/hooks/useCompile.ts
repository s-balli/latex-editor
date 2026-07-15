import { useRef, useCallback } from 'react';
import { startCompile, stopCompile } from '../api/compile';
import { writeFile } from '../api/files';
import { useCompileStore } from '../store/compileStore';
import { useEditorStore } from '../store/editorStore';

export function useCompile() {
  const wsRef = useRef<WebSocket | null>(null);
  const {
    engine, autoCompile, status, compileId,
    setStatus, clearOutput, addOutputLine, setResult, setCompileId,
  } = useCompileStore();
  const { activeTab, tabs, tabContents, markDirty } = useEditorStore();

  const compile = useCallback(async (path?: string) => {
    const targetPath = path || activeTab;
    if (!targetPath) return;

    // Önce kaydet
    const tab = tabs.find(t => t.path === targetPath);
    if (tab?.isDirty) {
      const content = tabContents[targetPath];
      if (content !== undefined) {
        await writeFile(targetPath, content);
        markDirty(targetPath, false);
      }
    }

    if (status === 'compiling') return;

    clearOutput();
    setStatus('compiling');

    try {
      const { compile_id } = await startCompile(targetPath, engine);
      setCompileId(compile_id);

      const ws = new WebSocket(`ws://localhost:8000/api/compile/${compile_id}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ path: targetPath, engine }));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'output') {
          const cleanLine = msg.line.replace(/\x1b\[[0-9;]*m/g, '');
          addOutputLine(cleanLine);
        } else if (msg.type === 'result') {
          setResult(msg.data);
          ws.close();
        } else if (msg.type === 'error') {
          setStatus('error');
          addOutputLine(`Hata: ${msg.message}`);
          ws.close();
        }
      };

      ws.onerror = () => {
        setStatus('error');
      };
    } catch (err) {
      setStatus('error');
      addOutputLine(`Hata: ${err}`);
    }
  }, [activeTab, tabs, tabContents, engine, status]);

  const stop = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (compileId) {
      stopCompile(compileId);
    }
    setStatus('idle');
  }, [compileId]);

  const saveAndCompile = useCallback(async () => {
    const targetPath = activeTab;
    if (!targetPath) return;

    // Kaydet
    const content = tabContents[targetPath];
    if (content !== undefined) {
      await writeFile(targetPath, content);
      markDirty(targetPath, false);
    }

    // Otomatik derle açıksa derle
    if (autoCompile) {
      compile(targetPath);
    }
  }, [activeTab, tabContents, autoCompile, compile]);

  return { compile, stop, saveAndCompile };
}
