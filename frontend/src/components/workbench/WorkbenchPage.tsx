/**
 * WorkbenchPage — 工作台顶层壳 (Phase 4 v0.6)
 *
 * 包装 WorkbenchLayout, 仅做 React.lazy 友好出口。
 */
import { WorkbenchLayout } from './WorkbenchLayout';

export function WorkbenchPage() {
  return <WorkbenchLayout />;
}