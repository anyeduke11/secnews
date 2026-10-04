/**
 * useAbortGuard — fetch 竞态守卫 (v0.8.6 P1-7, D5 裁决"先修竞态"落地)。
 *
 * 返回一个 ref, 组件卸载后 `current` 置 true。fetch effect 在 await 返回后
 * 先查守卫再 setState, 消除"快速切换路由/组件卸载后慢响应写脏状态"竞态:
 *
 *   const dead = useAbortGuard();
 *   const reload = useCallback(async () => {
 *     const d = await getJSON(url);
 *     if (dead.current) return;   // 已卸载 → 不写状态
 *     setData(d);
 *   }, []);
 *
 * 不引状态库 (D5 裁决 c: 维持现状只修竞态); 依赖变更序竞态 (同组件内
 * 连续 refetch 旧覆新) 由后续 requestId 方案承接, 本守卫只锁卸载面。
 */
import { useEffect, useRef } from 'react';

export function useAbortGuard() {
  const ref = useRef(false);
  useEffect(() => () => { ref.current = true; }, []);
  return ref;
}
