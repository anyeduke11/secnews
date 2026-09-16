// StatCard / StatStrip — B3 (DEV-0192) 编辑部统计卡
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatCard, StatStrip } from './StatCard';

describe('StatCard', () => {
  it('k/v/d 三插槽渲染', () => {
    render(<StatCard k="编目条目" v={12} d="wiki 镜像" />);
    expect(screen.getByText('编目条目')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('wiki 镜像')).toBeInTheDocument();
  });

  it('d 缺省时不渲染占位', () => {
    const { container } = render(<StatCard k="k" v="v" />);
    expect(container.querySelectorAll('.d').length).toBe(0);
  });
});

describe('StatStrip', () => {
  it('网格容器承载多卡', () => {
    render(
      <StatStrip>
        <StatCard k="a" v="1" />
        <StatCard k="b" v="2" />
      </StatStrip>,
    );
    expect(screen.getByTestId('stat-strip').querySelectorAll('[data-testid="stat-card"]').length).toBe(2);
  });
});
