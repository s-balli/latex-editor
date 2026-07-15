import { useState, useEffect, useCallback, useRef, type MouseEvent as ReactMouseEvent } from 'react';
import type { FileNode, InputNode } from '../../types';
import { listFiles, deleteFile, getInputTree } from '../../api/files';
import { startCompile } from '../../api/compile';
import { useCompileStore } from '../../store/compileStore';
import { useEditorStore } from '../../store/editorStore';
import './FileTree.css';

interface FileTreeProps {
  files?: FileNode[];
  onFileClick?: (path: string) => void;
  activeFilePath?: string;
}

interface FileTreeItemProps {
  node: FileNode;
  depth: number;
  onFileClick: (path: string) => void;
  onContextMenu: (e: ReactMouseEvent, node: FileNode) => void;
}

function getFileIcon(node: FileNode): string {
  if (node.type === 'dir') return '📁';
  if (node.name.endsWith('.tex')) return '📝';
  return '⚙';
}

function FileTreeItem({ node, depth, onFileClick, onContextMenu }: FileTreeItemProps) {
  const [expanded, setExpanded] = useState(false);
  const isDir = node.type === 'dir';

  const handleClick = useCallback(() => {
    if (isDir) {
      setExpanded(prev => !prev);
    }
  }, [isDir]);

  const handleDoubleClick = useCallback(() => {
    if (!isDir && onFileClick) {
      onFileClick(node.path);
    }
  }, [isDir, node.path, onFileClick]);

  const handleContextMenu = useCallback((e: ReactMouseEvent) => {
    e.preventDefault();
    onContextMenu(e, node);
  }, [onContextMenu, node]);

  const icon = getFileIcon(node);

  return (
    <li className="file-tree-item" role="treeitem">
      <div
        className={`file-tree-row ${isDir ? 'file-tree-row-dir' : 'file-tree-row-file'}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        onContextMenu={handleContextMenu}
        tabIndex={0}
      >
        <span className="file-tree-arrow">
          {isDir ? (expanded ? '▼' : '▶') : ''}
        </span>
        <span className="file-tree-icon">{icon}</span>
        <span className="file-tree-name" title={node.path}>{node.name}</span>
      </div>
      {isDir && expanded && node.children && node.children.length > 0 && (
        <ul className="file-tree-children" role="group">
          {node.children.map(child => (
            <FileTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              onFileClick={onFileClick}
              onContextMenu={onContextMenu}
            />
          ))}
        </ul>
      )}
      {isDir && expanded && (!node.children || node.children.length === 0) && (
        <div className="file-tree-empty" style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}>
          Empty folder
        </div>
      )}
    </li>
  );
}

function InputTreeItem({ node, depth, onFileClick }: { node: InputNode; depth: number; onFileClick: (path: string) => void }) {
  const hasChildren = node.children && node.children.length > 0;
  const isDir = node.is_dir === true;
  const [expanded, setExpanded] = useState(true);

  const handleClick = useCallback(() => {
    if (hasChildren) setExpanded(prev => !prev);
  }, [hasChildren]);

  const handleDoubleClick = useCallback(() => {
    if (!isDir) onFileClick(node.path);
  }, [isDir, node.path, onFileClick]);

  return (
    <li className="file-tree-item" role="treeitem">
      <div
        className={`file-tree-row ${isDir ? 'file-tree-row-dir' : 'file-tree-row-file'} file-tree-input-item`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
      >
        <span className="file-tree-arrow">
          {hasChildren ? (expanded ? '▼' : '▶') : ''}
        </span>
        <span className="file-tree-icon">{isDir ? '📁' : '📎'}</span>
        <span className="file-tree-name" title={node.path}>{node.name}</span>
      </div>
      {hasChildren && expanded && (
        <ul className="file-tree-children" role="group">
          {node.children.map(child => (
            <InputTreeItem key={child.path} node={child} depth={depth + 1} onFileClick={onFileClick} />
          ))}
        </ul>
      )}
    </li>
  );
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  node: FileNode | null;
}

const INITIAL_CONTEXT_MENU: ContextMenuState = {
  visible: false,
  x: 0,
  y: 0,
  node: null,
};

export default function FileTree({ files: externalFiles, onFileClick, activeFilePath }: FileTreeProps) {
  const [files, setFiles] = useState<FileNode[]>(externalFiles ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(INITIAL_CONTEXT_MENU);
  const [inputTree, setInputTree] = useState<InputNode[]>([]);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const engine = useCompileStore(s => s.engine);

  const refreshFiles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await listFiles();
      setFiles(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + auto-refresh every 3 seconds
  useEffect(() => {
    refreshFiles();
    const interval = setInterval(refreshFiles, 3000);
    return () => clearInterval(interval);
  }, [refreshFiles]);

  // Update files when external prop changes
  useEffect(() => {
    if (externalFiles !== undefined) {
      setFiles(externalFiles);
    }
  }, [externalFiles]);

  // Fetch input tree when active file changes
  useEffect(() => {
    if (!activeFilePath || !activeFilePath.endsWith('.tex')) {
      setInputTree([]);
      return;
    }
    let cancelled = false;
    getInputTree(activeFilePath)
      .then(tree => { if (!cancelled) setInputTree(tree); })
      .catch(() => { if (!cancelled) setInputTree([]); });
    return () => { cancelled = true; };
  }, [activeFilePath]);

  // Close context menu on click outside
  useEffect(() => {
    if (!contextMenu.visible) return;

    const handleClickOutside = (e: globalThis.MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(INITIAL_CONTEXT_MENU);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setContextMenu(INITIAL_CONTEXT_MENU);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [contextMenu.visible]);

  const handleFileClick = useCallback((path: string) => {
    if (onFileClick) {
      onFileClick(path);
    }
  }, [onFileClick]);

  const openTab = useEditorStore(s => s.openTab);

  const handleContextMenu = useCallback((e: ReactMouseEvent, node: FileNode) => {
    e.preventDefault();
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      node,
    });
  }, []);

  const handleCompile = useCallback(async () => {
    if (!contextMenu.node) return;
    const path = contextMenu.node.path;
    try {
      await startCompile(path, engine);
    } catch (err) {
      console.error('Compile failed:', err);
    }
    setContextMenu(INITIAL_CONTEXT_MENU);
  }, [contextMenu.node, engine]);

  const handleEdit = useCallback(() => {
    if (!contextMenu.node) return;
    openTab(contextMenu.node.path);
    if (onFileClick) {
      onFileClick(contextMenu.node.path);
    }
    setContextMenu(INITIAL_CONTEXT_MENU);
  }, [contextMenu.node, openTab, onFileClick]);

  const handleDelete = useCallback(async () => {
    if (!contextMenu.node) return;
    const confirmed = window.confirm(`"${contextMenu.node.name}" dosyasini silmek istediginize emin misiniz?`);
    if (!confirmed) return;
    try {
      await deleteFile(contextMenu.node.path);
      await refreshFiles();
    } catch (err) {
      console.error('Delete failed:', err);
    }
    setContextMenu(INITIAL_CONTEXT_MENU);
  }, [contextMenu.node, refreshFiles]);

  const isTexFile = contextMenu.node?.name.endsWith('.tex') ?? false;

  return (
    <div className="file-tree">
      <div className="file-tree-header">
        <span className="file-tree-title">DOSYALAR</span>
        <button
          className="file-tree-refresh"
          onClick={refreshFiles}
          disabled={loading}
          title="Yenile"
        >
          {loading ? '↻' : '↻'}
        </button>
      </div>
      <div className="file-tree-content">
        {error && (
          <div className="file-tree-error">Hata: {error}</div>
        )}
        {files.length === 0 && !error && !loading && (
          <div className="file-tree-empty-state">Dosya bulunamadi</div>
        )}
        <ul className="file-tree-root" role="tree">
          {files.map(node => (
            <FileTreeItem
              key={node.path}
              node={node}
              depth={0}
              onFileClick={handleFileClick}
              onContextMenu={handleContextMenu}
            />
          ))}
        </ul>
      </div>

      {inputTree.length > 0 && (
        <>
          <div className="file-tree-input-header">
            <span className="file-tree-title">BAĞLANTILI DOSYALAR</span>
          </div>
          <div className="file-tree-content">
            <ul className="file-tree-root" role="tree">
              {inputTree.map(node => (
                <InputTreeItem key={node.path} node={node} depth={0} onFileClick={handleFileClick} />
              ))}
            </ul>
          </div>
        </>
      )}

      {contextMenu.visible && (
        <div
          ref={contextMenuRef}
          className="file-tree-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          {isTexFile && (
            <button className="context-menu-item" onClick={handleCompile}>
              Derle
            </button>
          )}
          <button className="context-menu-item" onClick={handleEdit}>
            Duzenle
          </button>
          <button className="context-menu-item context-menu-item-danger" onClick={handleDelete}>
            Sil
          </button>
        </div>
      )}
    </div>
  );
}
