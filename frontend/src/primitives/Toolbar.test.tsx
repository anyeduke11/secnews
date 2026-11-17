import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Toolbar } from './Toolbar';

describe('Toolbar', () => {
  it('暴露 toolbar 角色与可访问名称', () => {
    render(<Toolbar aria-label="资讯筛选">x</Toolbar>);
    expect(screen.getByRole('toolbar', { name: '资讯筛选' })).toBeInTheDocument();
  });

  it('默认名称为"工具栏", 不产生无名区域', () => {
    render(<Toolbar>x</Toolbar>);
    expect(screen.getByRole('toolbar', { name: '工具栏' })).toBeInTheDocument();
  });

  it('trailing 区与主区分开挂载', () => {
    render(
      <Toolbar trailing={<button type="button">视图</button>}>
        <span>搜索</span>
      </Toolbar>
    );
    const bar = screen.getByRole('toolbar');
    expect(bar).toContainElement(screen.getByText('搜索'));
    expect(bar).toContainElement(screen.getByRole('button', { name: '视图' }));
  });
});