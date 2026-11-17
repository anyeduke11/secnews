// frontend/src/components/PageLayout.test.tsx
// Phase 6 — PageLayout 路由壳 + ToastProvider 测试
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { PageLayout } from './PageLayout';

describe('PageLayout', () => {
  beforeEach(() => {
    // 不需要 mock Toast — 真实渲染即可
  });

  it('renders children from <Outlet />', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div data-testid="child">Home Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.getByText('Home Content')).toBeInTheDocument();
  });

  it('renders child via nested route matching', () => {
    render(
      <MemoryRouter initialEntries={['/report']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>Home</div>} />
            <Route path="/report" element={<div>Report Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('Report Page')).toBeInTheDocument();
    expect(screen.queryByText('Home')).not.toBeInTheDocument();
  });

  it('renders nothing when no route matches (404)', () => {
    render(
      <MemoryRouter initialEntries={['/does-not-exist']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>Home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.queryByText('Home')).not.toBeInTheDocument();
  });

  it('wraps content in SentinelShell (唯一壳: 顶部横向导航 + 心跳条, 无左侧 AppNav)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>Hi</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    // 2026-09-13 NAV4: 工具页与四菜单页共用 SentinelShell 顶部横向导航 (唯一壳)
    expect(container.querySelector('div.sentinel')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '四菜单导航' })).toBeInTheDocument();
    // Phase 2 (DEV-0181): 心跳条改编辑部印务条 pressbar, 版面条 bandnav 上线
    expect(container.querySelector('section.pressbar')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '版面条' })).toBeInTheDocument();
    // 左侧 AppNav 已物理删除, 不得再出现第二套导航
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument();
    expect(container.querySelector('#main-content')).toBeInTheDocument();
  });

  it('B2: Toast 提到 App 根后, PageLayout 不依赖 Provider 祖先也能独立渲染', () => {
    // 2026-11-17: ToastProvider 上移到 App.tsx 根 (提示跨路由切换不丢);
    // 此处不再断言"内部挂载 Provider", 只锁布局骨架 — Provider 归属由 nav4_shell 守卫。
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>X</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(container.querySelector('div.sentinel')).toBeInTheDocument();
  });
});
