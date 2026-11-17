import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SplitPane } from './SplitPane';

describe('SplitPane', () => {
  it('两栏同时渲染, 辅助栏带无障碍名称', () => {
    render(<SplitPane main={<span>主区</span>} aside={<span>详情</span>} asideLabel="详情栏" />);
    expect(screen.getByText('主区')).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: '详情栏' })).toBeInTheDocument();
  });

  it('折叠后隐藏辅助栏内容, 不再出现在无障碍树中', () => {
    render(<SplitPane main={<span>主区</span>} aside={<span>详情</span>} asideLabel="详情栏" collapsed />);
    expect(screen.queryByText('详情')).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('折叠态提供展开入口并回调', () => {
    const onToggleAside = vi.fn();
    render(
      <SplitPane
        main={<span>主区</span>}
        aside={<span>详情</span>}
        asideLabel="详情栏"
        collapsed
        onToggleAside={onToggleAside}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '展开详情栏' }));
    expect(onToggleAside).toHaveBeenCalledOnce();
  });

  it('展开态提供收起入口, 并声明 expanded=true', () => {
    const onToggleAside = vi.fn();
    render(
      <SplitPane main={<span>主区</span>} aside={<span>详情</span>} asideLabel="详情栏" onToggleAside={onToggleAside} />
    );
    const btn = screen.getByRole('button', { name: '收起详情栏' });
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(btn);
    expect(onToggleAside).toHaveBeenCalledOnce();
  });
});