import type { ReactNode } from 'react';
import SplitPane from './SplitPane';
import './MainLayout.css';

interface MainLayoutProps {
  fileTree: ReactNode;
  editor: ReactNode;
  pdfViewer: ReactNode;
  outputPanel: ReactNode;
}

export default function MainLayout({ fileTree, editor, pdfViewer, outputPanel }: MainLayoutProps) {
  return (
    <div className="main-layout">
      <SplitPane direction="vertical" defaultSize={Math.round(window.innerHeight * 0.7)} minSize={150}>
        {/* Top pane: file tree | editor | pdf viewer */}
        <div className="main-layout-top">
          <SplitPane direction="horizontal" defaultSize={200} minSize={120}>
            <div className="main-layout-file-tree">{fileTree}</div>
            <SplitPane direction="horizontal" defaultSize={450} minSize={150}>
              <div className="main-layout-editor">{editor}</div>
              <div className="main-layout-pdf">{pdfViewer}</div>
            </SplitPane>
          </SplitPane>
        </div>
        {/* Bottom pane: output panel */}
        <div className="main-layout-output">{outputPanel}</div>
      </SplitPane>
    </div>
  );
}
