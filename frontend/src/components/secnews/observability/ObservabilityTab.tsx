/**
 * ObservabilityTab — /secnews/observability 路由壳
 *
 * v0.7 Batch ④: 顶部活跃告警横幅 (ActiveAlertsBanner) + 阈值规则编辑
 * (ThresholdEditor) 折叠面板. Dashboard 主体保持 Batch ③ 三卡片网格.
 * v0.8.6 P1-5 (DEV-0273): 质量门禁拒收回放区块 (审计 F1-3).
 */
import { ActiveAlertsBanner } from './ActiveAlertsBanner';
import { ObservabilityDashboard } from './ObservabilityDashboard';
import { RejectionReplay } from './RejectionReplay';
import { ThresholdEditor } from './ThresholdEditor';

export function ObservabilityTab() {
  return (
    <div className="flex flex-col gap-4">
      <ActiveAlertsBanner />
      <ObservabilityDashboard />
      <RejectionReplay />
      <ThresholdEditor />
    </div>
  );
}