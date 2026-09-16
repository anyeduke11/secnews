import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InfiniteCanvas, useCanvasCoords } from './InfiniteCanvas';

/** 读世界层的当前 transform (断言 pan/zoom 状态) */
function worldTransform(): string {
  const world = document.querySelector('.ic-world') as HTMLElement | null;
  return world?.style.transform ?? '';
}

/** jsdom 的 fireEvent.pointerDown 不携带 clientX (→ NaN), 用 MouseEvent 按
 *  pointer 类型名派发: React 按 type 字符串路由到 onPointerDown 等处理器 */
function firePointer(el: Element, type: string, x: number, y: number) {
  fireEvent(el, new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
}

describe('InfiniteCanvas — 无限画布共享组件 (Phase 5)', () => {
  it('渲染视口 + 世界 + children + 缩放控件', () => {
    render(
      <InfiniteCanvas ariaLabel="测试画布">
        <div data-canvas-node style={{ left: 10, top: 10 }}>节点A</div>
      </InfiniteCanvas>,
    );
    expect(screen.getByRole('application', { name: '测试画布' })).toBeInTheDocument();
    expect(screen.getByText('节点A')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(worldTransform()).toContain('scale(1)');
  });

  it('放大/缩小按钮居中缩放并更新百分比', () => {
    render(<InfiniteCanvas><div /></InfiniteCanvas>);
    fireEvent.click(screen.getByRole('button', { name: '放大' }));
    expect(screen.getByText('125%')).toBeInTheDocument();
    expect(worldTransform()).toContain('scale(1.25)');
    fireEvent.click(screen.getByRole('button', { name: '缩小' }));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('拖拽空白平移; 重置按钮与双击空白都回到原点', () => {
    render(<InfiniteCanvas ariaLabel="测试画布"><div /></InfiniteCanvas>);
    const viewport = screen.getByRole('application', { name: '测试画布' });
    firePointer(viewport, 'pointerdown', 100, 100);
    firePointer(viewport, 'pointermove', 160, 140);
    firePointer(viewport, 'pointerup', 160, 140);
    expect(worldTransform()).toContain('translate(60px,40px)');
    // 重置按钮
    fireEvent.click(screen.getByRole('button', { name: '重置视图' }));
    expect(worldTransform()).toContain('translate(0px,0px)');
    // 平移后双击空白同样重置
    firePointer(viewport, 'pointerdown', 100, 100);
    firePointer(viewport, 'pointermove', 150, 150);
    firePointer(viewport, 'pointerup', 150, 150);
    expect(worldTransform()).toContain('translate(50px,50px)');
    fireEvent.doubleClick(viewport);
    expect(worldTransform()).toContain('translate(0px,0px)');
  });

  it('ctrl+滚轮以光标为锚缩放 (deltaY>0 缩小 / <0 放大)', () => {
    render(<InfiniteCanvas ariaLabel="测试画布"><div /></InfiniteCanvas>);
    const viewport = screen.getByRole('application', { name: '测试画布' });
    fireEvent.wheel(viewport, { deltaY: 120, ctrlKey: true, clientX: 0, clientY: 0 });
    expect(worldTransform()).toContain('scale(0.95');
    fireEvent.click(screen.getByRole('button', { name: '重置视图' }));
    fireEvent.wheel(viewport, { deltaY: -120, ctrlKey: true, clientX: 0, clientY: 0 });
    expect(worldTransform()).toContain('scale(1.05');
  });

  it('A3: modifier 模式 — 纯滚轮不接管 (不 preventDefault, 视图不动), ctrl+滚轮仍缩放', () => {
    render(<InfiniteCanvas ariaLabel="测试画布" zoomOnWheel="modifier"><div /></InfiniteCanvas>);
    const viewport = screen.getByRole('application', { name: '测试画布' });

    const plain = new WheelEvent('wheel', { cancelable: true, bubbles: true, deltaY: 120, clientX: 0, clientY: 0 });
    fireEvent(viewport, plain);
    expect(plain.defaultPrevented).toBe(false);
    expect(worldTransform()).toContain('scale(1)');

    const mod = new WheelEvent('wheel', { cancelable: true, bubbles: true, deltaY: 120, ctrlKey: true, clientX: 0, clientY: 0 });
    fireEvent(viewport, mod);
    expect(mod.defaultPrevented).toBe(true);
    expect(worldTransform()).toContain('scale(0.95');
  });

  it('节点上的 pointerdown 不触发空白平移 (data-canvas-node 守卫)', () => {
    render(
      <InfiniteCanvas ariaLabel="测试画布">
        <div data-canvas-node style={{ left: 10, top: 10 }}>节点A</div>
      </InfiniteCanvas>,
    );
    const node = screen.getByText('节点A');
    firePointer(node, 'pointerdown', 100, 100);
    firePointer(node, 'pointermove', 300, 300);
    expect(worldTransform()).toContain('translate(0px,0px)');
  });

  it('useCanvasCoords: children 内消费坐标换算 (zoom 1.5625x 下 client 100/60 → 世界 64/38)', () => {
    let snapped = '';
    function Probe() {
      const coords = useCanvasCoords();
      return (
        <div
          data-canvas-node
          onPointerDown={e => {
            const w = coords.toWorld(e.clientX, e.clientY);
            snapped = `${w.x},${w.y}`;
          }}
        >
          探针
        </div>
      );
    }
    render(
      <InfiniteCanvas ariaLabel="测试画布">
        <Probe />
      </InfiniteCanvas>,
    );
    // 放大到 156.25% (1.25 × 1.25)
    fireEvent.click(screen.getByRole('button', { name: '放大' }));
    fireEvent.click(screen.getByRole('button', { name: '放大' }));
    expect(screen.getByText('156%')).toBeInTheDocument();
    firePointer(screen.getByText('探针'), 'pointerdown', 100, 60);
    // jsdom getBoundingClientRect 全 0 → 视口原点即 client 原点; pan=0 → world = client/zoom
    expect(snapped).toBe('64,38');
  });
});
