// KnowledgeCanvasPage — Phase 5 (DEV-0184) 双模式测试
// 画布模式 (默认): DOM 无限画布 + 可拖拽节点; 印厂 demo (ECharts) 只做源码级守卫
// (nav4_shell.test.tsx 锁 roam/draggable/DEMO_NODES), jsdom 无 canvas 2d 不实际挂载 ECharts。
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { KnowledgeCanvasPage } from './KnowledgeCanvasPage';

/** jsdom 的 fireEvent.pointer* 不携带 clientX — 用 MouseEvent 按 pointer 类型派发 */
function firePointer(el: Element, type: string, x: number, y: number) {
  fireEvent(el, new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
}

describe('KnowledgeCanvasPage — 无限画布 (Phase 5)', () => {
  it('默认画布模式: InfiniteCanvas 视口 + 8 个可拖拽节点 + 模式切换', () => {
    render(<KnowledgeCanvasPage />);
    expect(screen.getByTestId('infinite-canvas')).toBeInTheDocument();
    expect(screen.getByRole('application', { name: /知识画布/ })).toBeInTheDocument();
    expect(screen.getByTestId('canvas-node-collect')).toBeInTheDocument();
    expect(screen.getByTestId('canvas-node-replay')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /画布模式/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /印厂 demo/ })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('canvas-demo-note')).toBeInTheDocument();
  });

  it('缩放控件可用 (放大 → 125%)', () => {
    render(<KnowledgeCanvasPage />);
    fireEvent.click(screen.getByRole('button', { name: '放大' }));
    expect(screen.getByText('125%')).toBeInTheDocument();
  });

  it('节点拖拽: pointer 拖动更新节点世界坐标', () => {
    render(<KnowledgeCanvasPage />);
    const node = screen.getByTestId('canvas-node-collect');
    expect(node.style.left).toBe('100px');
    firePointer(node, 'pointerdown', 100, 100);
    firePointer(node, 'pointermove', 180, 150);
    firePointer(node, 'pointerup', 180, 150);
    expect(node.style.left).toBe('180px');
    expect(node.style.top).toBe('150px');
  });

  it('A6: 节点拖出初始域后, 边层 SVG 与画布 world 动态扩张 (+200px 边距)', () => {
    render(<KnowledgeCanvasPage />);
    const svg = document.querySelector('[data-testid="canvas-edgesvg"]') as SVGElement;
    expect(svg.getAttribute('width')).toBe('1400');
    expect(svg.getAttribute('height')).toBe('800');
    const node = screen.getByTestId('canvas-node-collect');
    firePointer(node, 'pointerdown', 100, 100);
    firePointer(node, 'pointermove', 1600, 900);
    firePointer(node, 'pointerup', 1600, 900);
    expect(node.style.left).toBe('1600px');
    // bounds = max(基础域, 最大节点坐标 + 200)
    expect(svg.getAttribute('width')).toBe('1800');
    expect(svg.getAttribute('height')).toBe('1100');
  });
});
