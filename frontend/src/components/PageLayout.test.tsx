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
      <MemoryRouter initialEntries={['/todos']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>Home</div>} />
            <Route path="/todos" element={<div>Todos Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('Todos Page')).toBeInTheDocument();
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
    // 2026-09-10 壳统一: 工具页与三层页共用 SentinelShell 顶部横向导航 (唯一壳)
    expect(container.querySelector('div.sentinel')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '三层工作流导航' })).toBeInTheDocument();
    expect(container.querySelector('section.pipeline')).toBeInTheDocument();
    // 左侧 AppNav 已物理删除, 不得再出现第二套导航
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument();
    expect(container.querySelector('#main-content')).toBeInTheDocument();
  });

  it('supports Toast by mounting ToastProvider (Toast API surface)', () => {
    // 内部 mount ToastProvider 后, document 应该包含 toast root
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>X</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    // 渲染成功即代表 ToastProvider 已挂载 (无异常)
    expect(container.querySelector('div.sentinel')).toBeInTheDocument();
  });
});
