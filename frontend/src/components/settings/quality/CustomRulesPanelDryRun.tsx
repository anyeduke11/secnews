/**
 * quality/CustomRulesPanelDryRun — dry-run 结果展示区块 (拆分自 CustomRulesPanel.tsx)
 *
 * 纯展示: dryRun 为空时不渲染任何 DOM, 命中列表/提示口径与原实现一致。
 */
import type { DryRunResult } from './CustomRulesPanel.types';

export function CustomRulesPanelDryRun({ dryRun }: { dryRun: DryRunResult | null }) {
  if (!dryRun) return null;
  return (
    <div className="st-cellnote" data-testid="dry-run-result">
      抽样 {dryRun.sampled} 条: 拒收命中 {dryRun.expert.reject_hits.length} ·
      扣分命中 {dryRun.expert.flag_hits.length} ·
      语义命中 {dryRun.semantic.hits.length} (判别 {dryRun.semantic.ran}/cap {dryRun.semantic.cap})
      {(dryRun.expert.reject_hits.length + dryRun.expert.flag_hits.length + dryRun.semantic.hits.length) === 0
        && ' — 无命中'}
      <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
        {[...dryRun.expert.reject_hits, ...dryRun.expert.flag_hits, ...dryRun.semantic.hits]
          .slice(0, 10).map(h => (
            <li key={h.item_id}>{h.title} — {h.reason}</li>
          ))}
      </ul>
      {dryRun.semantic.notes.length > 0 && (
        <p>语义侧提示: {dryRun.semantic.notes.join('; ')}</p>
      )}
    </div>
  );
}