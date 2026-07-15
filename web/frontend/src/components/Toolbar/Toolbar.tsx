import { useCompileStore } from '../../store/compileStore';
import './Toolbar.css';

interface ToolbarProps {
  onOpenFolder: () => void;
  onSave: () => void;
  onCompile: () => void;
  onStop: () => void;
}

export default function Toolbar({ onOpenFolder, onSave, onCompile, onStop }: ToolbarProps) {
  const { status, engine, autoCompile, setEngine, toggleAutoCompile } = useCompileStore();
  const compiling = status === 'compiling';

  return (
    <div className="toolbar">
      <div className="toolbar-group">
        <button className="toolbar-btn" onClick={onOpenFolder} title="Klasör Aç">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h3.172a1.5 1.5 0 0 1 1.06.44l.94.94H13.5A1.5 1.5 0 0 1 15 4.88v7.62a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9Z" stroke="currentColor" strokeWidth="1.2"/>
          </svg>
          <span>Klasör Aç</span>
        </button>

        <button className="toolbar-btn" onClick={onSave} title="Kaydet">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.5 1h8.69L14 3.81V13.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 13.5v-11A1.5 1.5 0 0 1 3.5 1h-1Z" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M5 1v3.5h5V1M5 9h6v5" stroke="currentColor" strokeWidth="1.2"/>
          </svg>
          <span>Kaydet</span>
        </button>

        <button
          className={`toolbar-btn ${compiling ? 'toolbar-btn--compiling' : ''}`}
          onClick={compiling ? onStop : onCompile}
          title={compiling ? 'Durdur' : 'Derle'}
        >
          {compiling ? (
            <>
              <svg className="toolbar-spinner" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="28 10"/>
              </svg>
              <span>Derleniyor...</span>
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 2l8 6-8 6V2Z" stroke="currentColor" strokeWidth="1.2" fill="currentColor" fillOpacity="0.3"/>
              </svg>
              <span>Derle</span>
            </>
          )}
        </button>
      </div>

      <div className="toolbar-group">
        <select
          className="toolbar-engine-select"
          value={engine}
          onChange={(e) => setEngine(e.target.value as 'lualatex' | 'pdflatex')}
          title="Derleme motoru"
        >
          <option value="lualatex">lualatex</option>
          <option value="pdflatex">pdflatex</option>
        </select>

        <button
          className={`toolbar-auto-toggle ${autoCompile ? 'toolbar-auto-toggle--on' : ''}`}
          onClick={toggleAutoCompile}
          title={autoCompile ? 'Otomatik derleme açık' : 'Otomatik derleme kapalı'}
        >
          {autoCompile ? (
            <span className="toggle-indicator toggle-indicator--on">&#9679;</span>
          ) : (
            <span className="toggle-indicator toggle-indicator--off">&#9675;</span>
          )}
          <span>{autoCompile ? 'Otomatik Derle' : 'Manuel'}</span>
        </button>
      </div>
    </div>
  );
}
