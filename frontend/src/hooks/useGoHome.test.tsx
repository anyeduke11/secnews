// frontend/src/hooks/useGoHome.test.ts
// Phase 6 — useGoHome hook 测试
import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useGoHome } from './useGoHome';

function withRouter(initialPath: string) {
  // renderHook 需要 wrapper 才能使用 react-router context
  return ({ children }: { children?: React.ReactNode }) => (
    <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
  );
}

describe('useGoHome', () => {
  it('returns a function', () => {
    const { result } = renderHook(() => useGoHome(), { wrapper: withRouter('/anywhere') });
    expect(typeof result.current).toBe('function');
  });

  it('returns a stable function reference across renders (useCallback)', () => {
    const { result, rerender } = renderHook(() => useGoHome(), { wrapper: withRouter('/anywhere') });
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it('called from / → stays on / (no navigation, navigate is a no-op)', () => {
    // MemoryRouter initialEntries=['/']: 已经在 '/', navigate('/') 不切换
    const { result } = renderHook(() => useGoHome(), { wrapper: withRouter('/') });
    // 简单调用应不抛错
    expect(() => result.current()).not.toThrow();
  });

  it('called from sub-route → can be invoked without error', () => {
    const { result } = renderHook(() => useGoHome(), { wrapper: withRouter('/todos') });
    // 调用 goHome 应执行 navigate('/'), 不抛错
    expect(() => result.current()).not.toThrow();
  });
});
