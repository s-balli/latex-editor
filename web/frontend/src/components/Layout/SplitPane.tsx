import { useState, useRef, useCallback, useEffect, type ReactNode, type MouseEvent } from 'react';
import './SplitPane.css';

interface SplitPaneProps {
  direction: 'horizontal' | 'vertical';
  defaultSize: number;
  children: [ReactNode, ReactNode];
  minSize?: number;
}

const MIN_SIZE = 100;

export default function SplitPane({ direction, defaultSize, children, minSize = MIN_SIZE }: SplitPaneProps) {
  const [size, setSize] = useState(defaultSize);
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: MouseEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (!containerRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      let newSize: number;

      if (direction === 'horizontal') {
        newSize = e.clientX - rect.left;
      } else {
        newSize = e.clientY - rect.top;
      }

      const containerSize = direction === 'horizontal' ? rect.width : rect.height;
      const maxSize = containerSize - minSize - 4; // 4px for the handle
      newSize = Math.max(minSize, Math.min(maxSize, newSize));

      setSize(newSize);
    };

    const handleMouseUp = () => {
      setDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, direction, minSize]);

  const isHorizontal = direction === 'horizontal';

  const containerStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: isHorizontal ? 'row' : 'column' as const,
    width: '100%',
    height: '100%',
    overflow: 'hidden',
  };

  const firstPaneStyle: React.CSSProperties = {
    flexBasis: `${size}px`,
    flexGrow: 0,
    flexShrink: 0,
    overflow: 'auto',
    minWidth: 0,
    minHeight: 0,
  };

  const handleStyle = {
    flexBasis: '4px',
    flexGrow: 0,
    flexShrink: 0,
  };

  const secondPaneStyle = {
    flexGrow: 1,
    overflow: 'auto',
    minWidth: 0,
    minHeight: 0,
  };

  return (
    <div ref={containerRef} className="split-pane" style={containerStyle}>
      <div className="split-pane-first" style={firstPaneStyle}>
        {children[0]}
      </div>
      <div
        className={`split-pane-handle ${dragging ? 'split-pane-handle-active' : ''} ${isHorizontal ? 'split-pane-handle-horizontal' : 'split-pane-handle-vertical'}`}
        style={handleStyle}
        onMouseDown={handleMouseDown}
      />
      <div className="split-pane-second" style={secondPaneStyle}>
        {children[1]}
      </div>
    </div>
  );
}
