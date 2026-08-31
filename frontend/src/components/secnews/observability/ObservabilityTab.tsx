/**
 * ObservabilityTab — /secnews/observability 路由壳
 *
 * v0.7 Batch ④: 顶部活跃告警横幅 (ActiveAlertsBanner) + 阈值规则编辑
 * (ThresholdEditor) 折叠面板. Dashboard 主体保持 Batch ③ 三卡片网格.
 */
import { ActiveAlertsBanner } from './ActiveAlertsBanner';
import { ObservabilityDashboard } from './ObservabilityDashboard';
import { ThresholdEditor } from './ThresholdEditor';

export function ObservabilityTab() {
  return (
    <div className="flex flex-col gap-4">
      <ActiveAlertsBanner />
      <ObservabilityDashboard />
      <ThresholdEditor />
    </div>
  );
}