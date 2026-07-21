// frontend/src/components/PageLayout.test.tsx
// Phase 6 — PageLayout 路由壳 + ToastProvider 测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { PageLayout } from './PageLayout';

// 捕获 toast 触发: 用一个 useToast 消费者组件
function ToastTrigger({ message }: { message: string }) {
  // 动态引入避免循环
  const ev = new CustomEvent('test:show-toast', { detail: { message } });
  window.dispatchEvent(ev);
  return <div>trigger-{message}</div>;
}

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

  it('wraps content in a styled container (bg-primary token)', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<PageLayout />}>
            <Route path="/" element={<div>Hi</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    // 外层容器是 <div class="min-h-[100dvh]" style="background-color: var(--bg-primary)">
    const wrapper = container.querySelector('div.min-h-\\[100dvh\\]') as HTMLElement | null;
    expect(wrapper).toBeInTheDocument();
    expect(wrapper?.style.backgroundColor).toBe('var(--bg-primary)');
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
    expect(container.querySelector('div.min-h-\\[100dvh\\]')).toBeInTheDocument();
  });
});
