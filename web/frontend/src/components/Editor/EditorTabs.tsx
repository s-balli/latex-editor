import './EditorTabs.css';

export interface TabInfo {
  path: string;
  name: string;
  isDirty: boolean;
}

export interface EditorTabsProps {
  tabs: TabInfo[];
  activeTab: string | null;
  onTabClick: (path: string) => void;
  onTabClose: (path: string) => void;
}

export default function EditorTabs({
  tabs,
  activeTab,
  onTabClick,
  onTabClose,
}: EditorTabsProps) {
  if (tabs.length === 0) return null;

  const handleMouseDown = (e: React.MouseEvent, path: string) => {
    if (e.button === 1) {
      // Middle-click closes the tab
      e.preventDefault();
      onTabClose(path);
    }
  };

  const handleClose = (e: React.MouseEvent, path: string) => {
    e.stopPropagation();
    onTabClose(path);
  };

  return (
    <div className="editor-tabs" role="tablist">
      {tabs.map((tab) => {
        const isActive = tab.path === activeTab;
        const label = tab.isDirty ? `*${tab.name}` : tab.name;

        return (
          <button
            key={tab.path}
            role="tab"
            aria-selected={isActive}
            className={`editor-tab${isActive ? ' editor-tab--active' : ''}`}
            title={tab.path}
            onClick={() => onTabClick(tab.path)}
            onMouseDown={(e) => handleMouseDown(e, tab.path)}
          >
            <span className="editor-tab__label">{label}</span>
            <span
              className="editor-tab__close"
              role="button"
              aria-label={`Close ${tab.name}`}
              onClick={(e) => handleClose(e, tab.path)}
            >
              &times;
            </span>
          </button>
        );
      })}
    </div>
  );
}
