// frontend/src/primitives/ToolPageHeader.test.tsx
// B9-b (2026-11-19): 工具页页头原子 (compact / bar 两体例) —— 断言 DOM 与类名口径。
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolPageHeader } from './ToolPageHeader';

describe('ToolPageHeader · compact 体例 (紧凑工具头)', () => {
  it('渲染等宽前缀 + 标题于 h1, 容器带 2px 下边线', () => {
    render(<ToolPageHeader variant="compact" prefix="TAG" title="标签管理" />);
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1).toHaveTextContent('TAG');
    expect(h1).toHaveTextContent('标签管理');
    expect(h1.className).toBe('text-sm font-bold tracking-wide');
    expect(h1.querySelector('.font-mono')?.textContent).toBe('TAG');
    // 容器: 紧凑横排 + 2px 下边线
    const container = h1.parentElement as HTMLElement;
    expect(container.className).toBe('flex items-center justify-between pb-2 mb-1');
    expect(container.style.borderBottom).toBe('2px solid var(--text-primary)');
  });

  it('返回钮点击触发 onBack, 且带「返回」无障碍名与图标', () => {
    const onBack = vi.fn();
    render(<ToolPageHeader variant="compact" prefix="FIND" title="统一搜索" onBack={onBack} />);
    const btn = screen.getByRole('button', { name: '返回' });
    expect(btn.className).toBe('btn-ghost gap-1.5 px-2 py-1 text-[10px]');
    expect(btn.querySelector('svg')).not.toBeNull();
    fireEvent.click(btn);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('未传 onBack 则不渲染返回钮', () => {
    render(<ToolPageHeader variant="compact" prefix="EXT" title="自动标签提取" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('ToolPageHeader · bar 体例 (横条头)', () => {
  it('标题为 text-lg font-bold, 返回钮在左且带自定义无障碍名', () => {
    render(
      <ToolPageHeader
        title="技能详情"
        onBack={() => {}}
        backLabel="返回商店"
      />,
    );
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1.className).toBe('text-lg font-bold');
    const container = h1.parentElement as HTMLElement;
    expect(container.tagName).toBe('HEADER');
    expect(container.className).toBe('flex items-center gap-3');
    const btn = screen.getByRole('button', { name: '返回商店' });
    expect(container.firstElementChild).toBe(btn);
    expect(btn.className).toBe('h-8 px-2.5 rounded-md text-sm border');
  });

  it('truncate 时标题带截断类名 (长名场景)', () => {
    render(<ToolPageHeader title="一个非常长的技能名称" truncate />);
    expect(screen.getByRole('heading', { level: 1 }).className).toBe('text-lg font-bold truncate');
  });

  it('trailing 槽渲染在标题之后 (计数/徽标)', () => {
    render(
      <ToolPageHeader
        title="技能商店"
        trailing={<span data-testid="count">12 / 30 项</span>}
      />,
    );
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1.nextElementSibling?.getAttribute('data-testid')).toBe('count');
  });

  it('未传 onBack 则不渲染返回钮', () => {
    render(<ToolPageHeader title="新建 Skill" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
