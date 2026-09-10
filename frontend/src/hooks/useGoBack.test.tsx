// frontend/src/hooks/useGoBack.test.tsx
// 2026-09-10 壳统一 — 工具页「返回」统一为智能返回 (有来路回上一页, 否则回 fallback)
import { describe, it, expect, beforeEach } from 'vitest';
import { render, renderHook, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { useGoBack } from './useGoBack';

function withRouter(initialPath: string) {
  return ({ children }: { children?: React.ReactNode }) => (
    <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
  );
}

/** 探针: 渲染返回按钮 + 当前路径 (MemoryRouter 自己维护栈, hook 只读 window.history.state.idx 做决策) */
function Probe({ fallback }: { fallback?: string }) {
  const goBack = useGoBack(fallback);
  const loc = useLocation();
  return (
    <>
      <button type="button" onClick={goBack}>返回</button>
      <div data-testid="loc">{loc.pathname}</div>
    </>
  );
}

describe('useGoBack', () => {
  beforeEach(() => {
    // jsdom 的 history.state 会跨用例残留, 每例回到「无站内栈深度」
    window.history.replaceState(null, '');
  });

  it('returns a stable function reference across renders (useCallback)', () => {
    const { result, rerender } = renderHook(() => useGoBack(), { wrapper: withRouter('/anywhere') });
    expect(typeof result.current).toBe('function');
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it('无来路 (history.state 无 idx) → 回默认 fallback /', () => {
    render(
      <MemoryRouter initialEntries={['/todos']}>
        <Probe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(screen.getByTestId('loc').textContent).toBe('/');
  });

  it('无来路 + 自定义 fallback → 回 fallback (详情页回商店)', () => {
    render(
      <MemoryRouter initialEntries={['/skill-store/cve-impact-brief']}>
        <Probe fallback="/skill-store" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(screen.getByTestId('loc').textContent).toBe('/skill-store');
  });

  it('站内有上一页 (idx > 0) → navigate(-1) 回来路而非首页', () => {
    window.history.replaceState({ idx: 1 }, '');
    render(
      <MemoryRouter initialEntries={['/judge', '/settings']} initialIndex={1}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('loc').textContent).toBe('/settings');
    fireEvent.click(screen.getByRole('button', { name: '返回' }));
    expect(screen.getByTestId('loc').textContent).toBe('/judge');
  });
});
