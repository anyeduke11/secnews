/**
 * InfiniteCanvas — 无限画布共享组件 (Phase 5, DEV-0184, 对齐方案B 原型)
 *
 * 结构: .ic-viewport (视口, overflow hidden + 点阵网格) > .ic-world (世界, transform) > children
 * 交互 (方案B 原型逐字移植, 令牌化改造):
 *  - 拖拽空白处平移 (pointer capture); ctrl/⌘+滚轮以光标为锚缩放; 触控板横向滚 = 平移;
 *    纵向滚 = 缩放; 双击空白重置; 右下角缩放控件 (+/−/百分比/重置)
 *  - 缩放区间 0.05–8, transform-origin 0 0
 * 节点拖拽: children 内的元素标记 data-canvas-node (避免与空白平移抢事件),
 *  经 useCanvasCoords() 把 client 坐标换算为世界坐标后自行 setState
 *  (消费方: SentinelGraphPage 画布模式; 原 demo 页 /knowledge/canvas 已于 DEV-0295 退役),
 *  本组件只管视口。
 * 主题: 全部走全局 token — dark 主题即方案B 的深色画布, paper 主题为暖纸画布。
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import './canvas.css';

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 8;
const ZOOM_IN_FACTOR = 1.25;
const ZOOM_OUT_FACTOR = 0.8;

export interface CanvasCoords {
  x: number;
  y: number;
  zoom: number;
  /** client 坐标 → 世界坐标 (视口左上为原点) */
  toWorld: (clientX: number, clientY: number) => { x: number; y: number };
}

const CanvasContext = createContext<CanvasCoords>({
  x: 0, y: 0, zoom: 1,
  toWorld: (cx, cy) => ({ x: cx, y: cy }),
});

/** children 内消费: 节点拖拽时换算世界坐标 */
export function useCanvasCoords(): CanvasCoords {
  return useContext(CanvasContext);
}

export function InfiniteCanvas({
  children,
  height = 640,
  worldWidth = 4000,
  worldHeight = 3000,
  ariaLabel = '无限画布',
  className = '',
  zoomOnWheel = 'always',
  onTransformChange,
}: {
  children?: React.ReactNode;
  /** 视口高度 (画布嵌入页面文档流, 非全屏 fixed) */
  height?: number;
  worldWidth?: number;
  worldHeight?: number;
  ariaLabel?: string;
  className?: string;
  /** A3 (DEV-0188): 滚轮接管策略 — always=纯滚轮也缩放 (方案B 原型语义, 默认);
   *  modifier=仅 ctrl/⌘+滚轮缩放, 纯滚轮交还页面滚动 */
  zoomOnWheel?: 'always' | 'modifier';
  /** 变换回调 (pan/zoom 任一变化即触发; 消费方自行量化去抖, 用于 zoom 感知渲染) */
  onTransformChange?: (t: { x: number; y: number; zoom: number }) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [t, setT] = useState({ x: 0, y: 0, zoom: 1 });
  const [panning, setPanning] = useState(false);
  const dragRef = useRef<{ sx: number; sy: number } | null>(null);

  const toWorld = useCallback((clientX: number, clientY: number) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    const left = clientX - (rect?.left ?? 0);
    const top = clientY - (rect?.top ?? 0);
    return { x: Math.round((left - t.x) / t.zoom), y: Math.round((top - t.y) / t.zoom) };
  }, [t]);

  const coords = useMemo<CanvasCoords>(() => ({ x: t.x, y: t.y, zoom: t.zoom, toWorld }), [t, toWorld]);

  /** 以视口内某点为锚缩放 (保持该点下的世界坐标不动) */
  const zoomAt = useCallback((mx: number, my: number, factor: number) => {
    setT(cur => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, cur.zoom * factor));
      const wx = (mx - cur.x) / cur.zoom;
      const wy = (my - cur.y) / cur.zoom;
      return { zoom, x: mx - wx * zoom, y: my - wy * zoom };
    });
  }, []);

  // A3 修正 (DEV-0188): React 17+ 对根级 wheel 监听强制 passive, 合成 onWheel 里
  // preventDefault 无效 (页面会跟着滚)。改挂原生非 passive 监听, 缩放/平移才真正接管滚轮。
  const handleWheel = useCallback((e: WheelEvent) => {
    const mod = e.ctrlKey || e.metaKey;
    // modifier 模式下纯滚轮交还页面滚动 (不接管、不 preventDefault)
    if (zoomOnWheel === 'modifier' && !mod) return;
    e.preventDefault();
    const rect = viewportRef.current?.getBoundingClientRect();
    const mx = e.clientX - (rect?.left ?? 0);
    const my = e.clientY - (rect?.top ?? 0);
    if (mod) {
      // 捏合 / ⌘+滚轮: 光标锚定缩放
      zoomAt(mx, my, e.deltaY > 0 ? 0.95 : 1.05);
      return;
    }
    // 触控板双指横向滚动 → 平移 (方案B 语义); 纵向滚动 → 缩放
    const hasX = Math.abs(e.deltaX) > 0.5;
    if (hasX || Math.abs(e.deltaX) > Math.abs(e.deltaY) * 0.3) {
      setT(cur => ({ ...cur, x: cur.x - e.deltaX, y: cur.y - e.deltaY }));
    } else {
      zoomAt(mx, my, e.deltaY > 0 ? 0.95 : 1.05);
    }
  }, [zoomAt, zoomOnWheel]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [handleWheel]);

  // A4 配套: 变换回调 (消费方如 graph 画布用它做 zoom 感知命中补偿)
  useEffect(() => {
    onTransformChange?.(t);
  }, [t, onTransformChange]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // 节点元素 (data-canvas-node) 自行处理拖拽, 不触发空白平移
    const target = e.target as HTMLElement;
    if (target.closest('[data-canvas-node]')) return;
    dragRef.current = { sx: e.clientX - t.x, sy: e.clientY - t.y };
    setPanning(true);
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // jsdom 无 setPointerCapture — 测试环境忽略
    }
    e.preventDefault();
  }, [t.x, t.y]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    setT(cur => ({ ...cur, x: e.clientX - d.sx, y: e.clientY - d.sy }));
  }, []);

  const endPan = useCallback(() => {
    dragRef.current = null;
    setPanning(false);
  }, []);

  const onDoubleClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest('[data-canvas-node]')) return;
    setT({ x: 0, y: 0, zoom: 1 });
  }, []);

  const zoomCentered = useCallback((factor: number) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    zoomAt((rect?.width ?? 800) / 2, (rect?.height ?? 600) / 2, factor);
  }, [zoomAt]);

  // 点阵网格: 网格距随缩放, 偏移随平移 (方案B updateGrid 移植)
  const grid = 40 * t.zoom;
  const gridStyle: React.CSSProperties = {
    backgroundImage: 'radial-gradient(circle, var(--ic-grid) 0.8px, transparent 0.8px)',
    backgroundSize: `${grid}px ${grid}px`,
    backgroundPosition: `${t.x % grid}px ${t.y % grid}px`,
  };

  return (
    <CanvasContext.Provider value={coords}>
      <div className={`ic-root ${className}`} data-testid="infinite-canvas">
        <div
          ref={viewportRef}
          className={`ic-viewport${panning ? ' panning' : ''}`}
          style={{ height, ...gridStyle }}
          role="application"
          aria-label={ariaLabel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endPan}
          onPointerCancel={endPan}
          onDoubleClick={onDoubleClick}
        >
          <div
            className="ic-world"
            style={{ width: worldWidth, height: worldHeight, transform: `translate(${t.x}px,${t.y}px) scale(${t.zoom})` }}
          >
            {children}
          </div>
        </div>
        <div className="ic-controls" role="group" aria-label="缩放控件">
          <button type="button" className="ic-zbtn" aria-label="放大" onClick={() => zoomCentered(ZOOM_IN_FACTOR)}>+</button>
          <span className="ic-zlabel num" aria-live="polite">{Math.round(t.zoom * 100)}%</span>
          <button type="button" className="ic-zbtn" aria-label="缩小" onClick={() => zoomCentered(ZOOM_OUT_FACTOR)}>−</button>
          <button type="button" className="ic-zbtn ic-zreset" aria-label="重置视图" title="双击空白处也可重置" onClick={() => setT({ x: 0, y: 0, zoom: 1 })}>⟲</button>
        </div>
      </div>
    </CanvasContext.Provider>
  );
}
