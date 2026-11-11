/**
 * 行动四段指挥台 · 第④段 Artifact (R-15)
 * 数据源: GET /api/v1/cases/{id}/aggregate → artifacts (既有端点)
 * 只读呈现产物 + 证据回执: 验收时间 / 验证结论 (pass/fail/warn)。
 */
// 类型取 API 层: 本组件的唯一数据源是 CaseAggregate.artifacts (api/v1.ts 定义)。
// api/v1.ts 的枚举已回归 codegen 真源 domain/v1_0.ts, Artifact 亦由真源派生, 无漂移。
import type { Artifact } from '../../../api/v1';
import {
  STAGE,
  STAGE_HEAD,
  STAGE_TITLE,
  STAGE_COUNT,
  STAGE_EMPTY,
  ITEM_ROW,
  TONE_OK,
  TONE_WARN,
  TONE_IDLE,
} from './stageStyles';

const KIND: Record<string, string> = {
  report: '报告',
  file: '文件',
  data: '数据',
  chart: '图表',
  code_patch: '代码补丁',
  message: '消息',
};

function size(n: number): string {
  return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`;
}

function receiptOf(a: Artifact): { label: string; color: string } {
  if (a.accepted_at) return { label: '已验收 · 回执已签署', color: TONE_OK };
  if (a.verified_result === 'pass') return { label: '已验证 · 待验收', color: TONE_OK };
  if (a.verified_result === 'fail') return { label: '验证失败', color: TONE_WARN };
  if (a.verified_result === 'warn') return { label: '验证告警', color: TONE_WARN };
  return { label: '待验证', color: TONE_IDLE };
}

interface ArtifactStageProps {
  caseId: string | null;
  items: Artifact[];
  loading: boolean;
  error: string | null;
}

export function ArtifactStage({ caseId, items, loading, error }: ArtifactStageProps) {
  return (
    <section data-stage="artifact" style={STAGE} aria-label="Artifact 产物段">
      <div style={STAGE_HEAD}>
        <span style={STAGE_TITLE}>④ Artifact · 产物与回执</span>
        <span style={STAGE_COUNT}>{items.length} 件</span>
      </div>

      {!caseId && <p style={STAGE_EMPTY}>先在上方选择案件，产物随 Run 完成后回填。</p>}
      {caseId && loading && <p style={STAGE_EMPTY}>加载产物…</p>}
      {caseId && !loading && error && (
        <p style={{ ...STAGE_EMPTY, color: 'var(--sn-amber)' }}>产物不可用：{error}</p>
      )}
      {caseId && !loading && !error && items.length === 0 && (
        <p style={STAGE_EMPTY}>该案件暂无 Artifact（Run 完成后回填）。</p>
      )}

      {caseId && !loading && !error && items.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
          {items.map(a => {
            const r = receiptOf(a);
            return (
              <li key={a.id} data-testid="artifact-stage-item" style={ITEM_ROW}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ color: 'var(--sn-ink)', fontSize: 12, fontWeight: 600 }}>{a.title}</span>
                  <span style={{ fontSize: 11, color: 'var(--sn-ink-3)' }}>
                    {KIND[a.kind] ?? a.kind} · {a.format} · {size(a.size_bytes)}
                  </span>
                </div>
                <div style={{ marginTop: 4, fontSize: 11, color: r.color }}>{r.label}</div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}