/**
 * useGoHome — Phase 1A 路由工具 hook
 *
 * 替代 12 个 page 组件的 onBack={goHome} prop 模式。
 *
 * 用法:
 *   // 之前
 *   function TodosPage({ onBack }: { onBack: () => void }) {
 *     return <button onClick={onBack}>返回</button>;
 *   }
 *
 *   // 之后
 *   function TodosPage() {
 *     const goHome = useGoHome();
 *     return <button onClick={goHome}>返回</button>;
 *   }
 */
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export function useGoHome() {
  const navigate = useNavigate();
  return useCallback(() => navigate('/'), [navigate]);
}
