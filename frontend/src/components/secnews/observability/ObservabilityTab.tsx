/**
 * ObservabilityTab — /secnews/observability 路由壳
 *
 * 直接挂 ObservabilityDashboard; 未来 Batch ④ 在此顶部加告警横幅 +
 * 阈值编辑折叠面板。
 */
import { ObservabilityDashboard } from './ObservabilityDashboard';

export function ObservabilityTab() {
  return <ObservabilityDashboard />;
}