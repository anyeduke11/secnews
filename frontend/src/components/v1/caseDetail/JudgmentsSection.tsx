/**
 * JudgmentsSection — 判断 (Judgment) 区块 + v0.8.6 M1「AI 起草研判」入口
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/data-testid/section 锚点逐字不变)
 *
 * 起草走提案审批流 (容器 handler), draft→publish 按钮走 allowed_actions 守卫。
 */
import type { Judgment } from '../../../domain/v1_0';
import { renderInlineMarkdown } from '../../../lib/markdown';
import { Badge } from './CaseBadge';

interface Props {
  judgments: Judgment[];
  loading: boolean;
  generating: 'judgment' | 'action' | null;
  evidenceCount: number;
  pendingMutation: string | null;
  onGenerate: () => void;
  onPublish: (j: Judgment) => void;
}

export function JudgmentsSection({ judgments, loading, generating, evidenceCount, pendingMutation, onGenerate, onPublish }: Props) {
  return (
    <div id="section-judgments" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          判断 (Judgment) {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
        {/* v0.8.6 M1: AI 起草研判 → 提案送审 (/action 收件箱); 证据来自 D1.2 立项绑定 */}
        <button
          type="button"
          onClick={onGenerate}
          disabled={generating !== null || evidenceCount === 0}
          title={evidenceCount === 0 ? '需先携带证据材料 (从信号立项)' : 'HEAVY 档生成研判草案, 送行动菜单审批收件箱'}
          className="text-xs px-3 py-1.5 rounded font-medium focus-ring disabled:opacity-50"
          style={{ background: 'var(--color-info)', color: 'var(--text-on-info, #fff)' }}
          data-testid="generate-judgment-btn"
        >
          {generating === 'judgment' ? '起草中…' : 'AI 起草研判'}
        </button>
      </div>
      {judgments.length === 0 ? (
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无判断</div>
      ) : (
        <div className="space-y-3">
          {judgments.map(j => (
            <div key={j.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
              <div className="flex items-center gap-2 mb-2">
                <Badge color={j.status === 'published' ? 'green' : j.status === 'draft' ? 'yellow' : 'gray'}>{j.status}</Badge>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {j.claim_type} · confidence: {j.confidence} · rev {j.revision}
                </span>
                {/* D2: draft → 人工发布 (三重守卫, allowed_actions 守卫) */}
                {j.status === 'draft' && Array.isArray(j.allowed_actions) && j.allowed_actions.includes('publish') && (
                  <button
                    onClick={() => onPublish(j)}
                    disabled={pendingMutation === `publish:${j.id}`}
                    className="text-xs px-2.5 py-0.5 rounded font-medium focus-ring disabled:opacity-50"
                    style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                    data-testid="publish-judgment-btn"
                  >
                    {pendingMutation === `publish:${j.id}` ? '发布中…' : '发布'}
                  </button>
                )}
              </div>
              {/* T11: claim 是 Markdown, 自实现 renderInlineMarkdown 渲染 (**bold** / 列表 / 标题) */}
              <div
                className="text-sm prose-sm"
                style={{ color: 'var(--text-primary)' }}
                dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(j.claim) }}
              />
              {j.conditions && (
                <div className="text-xs mt-2 italic" style={{ color: 'var(--text-muted)' }}>
                  适用条件: {j.conditions}
                </div>
              )}
              {j.unknowns && j.unknowns.length > 0 && (
                <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>
                  未知项: {j.unknowns.join('; ')}
                </div>
              )}
              {j.evidence_refs && j.evidence_refs.length > 0 && (
                <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                  证据 ({j.evidence_refs.length} 条): {j.evidence_refs.map(e => e.material_id).join(', ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
