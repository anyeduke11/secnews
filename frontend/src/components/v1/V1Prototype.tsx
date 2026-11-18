/**
 * V1Prototype — v1 知识目录视图 (v0.8.5 后唯一保留的 v1 页面形态).
 *
 * v0.8.5 D2 清理: WorkbenchView / IntelView / CasesView 与 WorkbenchPage / IntelPage /
 * CasesPage / V1Prototype 别名已删除 — 三层 Sentinel 为唯一壳 (spec = docs/v0.8.5/V0.8.5_PLAN.md),
 * 对应能力已由 SignalPanel / CaseQueuePanel / ExecOverviewPanel 三区块 + /cases/:caseId 深链承接。
 * 本文件仅承载:
 *   - KnowledgeView  → /knowledge/v1 (KnowledgeV1Page, 知识目录 + 采用/生命周期)
 *   - CaseDetail/Badge → './CaseDetail' re-export (旧测试 import 路径兼容)
 *
 * 数据: 全部走真实 API, 失败显 unavailable, 不再 mock fallback.
 */

import { useSSEWithRefetch } from './useSSEWithRefetch';
import { KnowledgeView } from './V1PrototypeKnowledgeView';

// ---------------------------------------------------------------------------
// 页面: /knowledge/v1 (更多 → 知识库 → v1 目录)
// ---------------------------------------------------------------------------

export function KnowledgeV1Page() {
  // T17.5: v1_* 事件 → toast (fire-and-forget)
  void useSSEWithRefetch(() => {});
  return (
    <div className="max-w-6xl mx-auto p-6">
      <KnowledgeView />

      {/* 走查说明 */}
      <div className="mt-8 p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
        <h3 className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>走查 3 路径说明</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-warning)' }}>缺资产</div>
            <div>Case 下有 Action, 但 Action 的 Run 未产出 Artifact, 或 expected_artifacts 为空。</div>
          </div>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-info)' }}>待验收</div>
            <div>Artifact 已通过自动验证 (verified), 等待业务验收 (acceptance) 才能标记 accepted。</div>
          </div>
          <div>
            <div className="font-medium mb-1" style={{ color: 'var(--color-error)' }}>失败</div>
            <div>Run 或 Action 状态为 failed, 需查看 error 字段决定重试 (retry) 或升级 (escalate)。</div>
          </div>
        </div>
      </div>
    </div>
  );
}