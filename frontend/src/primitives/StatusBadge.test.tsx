import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('始终渲染文字标签 (颜色不得单独表义)', () => {
    render(<StatusBadge tone="risk">高危</StatusBadge>);
    expect(screen.getByText('高危')).toBeInTheDocument();
  });

  it('携带 data-tone 供样式与测试定位语义', () => {
    render(<StatusBadge tone="warn">待处理</StatusBadge>);
    expect(screen.getByText('待处理').closest('[data-tone]')).toHaveAttribute('data-tone', 'warn');
  });

  it('dot 仅装饰: 不产生可读文字节点', () => {
    const { container } = render(
      <StatusBadge tone="ok" dot>
        已确认
      </StatusBadge>
    );
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
    expect(screen.getByText('已确认')).toBeInTheDocument();
  });

  it('count 作为右侧次要数字渲染', () => {
    render(
      <StatusBadge tone="neutral" count={12}>
        全部
      </StatusBadge>
    );
    expect(screen.getByText('12')).toBeInTheDocument();
  });
});