/**
 * useAbortGuard 单测 (v0.8.6 P1-7 竞态守卫契约)。
 *
 * WHY (Rule 9): 守卫是 P1-7 全部 24 个 fetch effect 的竞态防线 —
 * 锁「卸载前 false / 卸载后 true / 挂载期 rerender 不翻转」三支契约,
 * 任何破坏都会让下游 24 处守卫失效为永假或永真。
 */
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAbortGuard } from './useAbortGuard';

describe('useAbortGuard', () => {
  it('挂载期 current=false (守卫放行正常写状态)', () => {
    const { result } = renderHook(() => useAbortGuard());
    expect(result.current.current).toBe(false);
  });

  it('卸载后 current=true (守卫拦截慢响应写状态)', () => {
    const { result, unmount } = renderHook(() => useAbortGuard());
    expect(result.current.current).toBe(false);
    unmount();
    expect(result.current.current).toBe(true);
  });

  it('挂载期 rerender 不翻转 (依赖变更重渲染不影响守卫)', () => {
    const { result, rerender } = renderHook(() => useAbortGuard());
    rerender();
    rerender();
    expect(result.current.current).toBe(false);
  });
});
