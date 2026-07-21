// frontend/src/components/CategoryNav.test.tsx
// Phase 6 — CategoryNav 分类导航测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CategoryNav } from './CategoryNav';

describe('CategoryNav', () => {
  it('renders all category buttons', () => {
    render(
      <CategoryNav
        active="all"
        onChange={vi.fn()}
        counts={{ all: 10, ai: 3, security: 2 }}
      />
    );
    // 来自 CATEGORIES 常量
    expect(screen.getByText('全部热点')).toBeInTheDocument();
    expect(screen.getByText(/科技/)).toBeInTheDocument();
    expect(screen.getByText('网络安全')).toBeInTheDocument();
  });

  it('clicking a category calls onChange with the id', () => {
    const onChange = vi.fn();
    render(
      <CategoryNav
        active="all"
        onChange={onChange}
        counts={{}}
      />
    );
    fireEvent.click(screen.getByText('网络安全'));
    expect(onChange).toHaveBeenCalledWith('security');
  });

  it('displays count badge when count > 0', () => {
    render(
      <CategoryNav
        active="all"
        onChange={vi.fn()}
        counts={{ all: 100, ai: 5, security: 0 }}
      />
    );
    // all 计数 = 100 + 5 + 0 = 105 (sum)
    expect(screen.getByText('105')).toBeInTheDocument();
  });

  it('hides count badge when count is 0', () => {
    render(
      <CategoryNav
        active="ai"
        onChange={vi.fn()}
        counts={{ ai: 0, security: 3 }}
      />
    );
    // ai 计数为 0, 不显示
    const aiBtn = screen.getByText(/科技/).closest('button')!;
    expect(aiBtn.textContent).not.toContain('0');
  });

  it('all category shows sum of all counts', () => {
    render(
      <CategoryNav
        active="all"
        onChange={vi.fn()}
        counts={{ ai: 5, security: 3, finance: 2, startup: 1, bid: 4, github: 0 }}
      />
    );
    // 全部 = 5 + 3 + 2 + 1 + 4 + 0 = 15
    expect(screen.getByText('15')).toBeInTheDocument();
  });

  it('shows drift warning when consistencyDrift provided', () => {
    render(
      <CategoryNav
        active="all"
        onChange={vi.fn()}
        counts={{}}
        consistencyDrift={[
          { category: 'ai', cached: 10, db: 5, note: 'test' },
        ]}
      />
    );
    expect(screen.getByText('⚠️')).toBeInTheDocument();
  });

  it('does not show drift warning for non-drift categories', () => {
    render(
      <CategoryNav
        active="all"
        onChange={vi.fn()}
        counts={{}}
        consistencyDrift={[]}
      />
    );
    expect(screen.queryByText('⚠️')).not.toBeInTheDocument();
  });
});
