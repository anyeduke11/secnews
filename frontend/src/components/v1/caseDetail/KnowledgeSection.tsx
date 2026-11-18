/**
 * KnowledgeSection — T13 知识 (Knowledge) 区块: 复用回执 + 复查 + body 摘要
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/data-testid/section 锚点逐字不变)
 *
 * 数据由容器 aggregate 拉取后下发 (listKnowledge + getKnowledgeReuse), 本区块不发任何请求。
 */
import type { Knowledge, ReuseReceipt } from '../../../api/v1';
import { renderInlineMarkdown } from '../../../lib/markdown';
import { Badge } from './CaseBadge';
import type { ReuseSummary } from './caseDetailModel';

interface Props {
  items: Knowledge[];
  receipts: Record<string, ReuseReceipt>;
  reuseSummary: ReuseSummary | null;
  loading: boolean;
}

export function KnowledgeSection({ items, receipts, reuseSummary, loading }: Props) {
  return (
    <div id="section-knowledge" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          知识 (Knowledge) {loading && <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>加载中…</span>}
        </h3>
      </div>
      {/* D4: 复利卡 — 真实回执计数, 不做无基线的「节省 X」估算 */}
      {reuseSummary && reuseSummary.adoptions_total > 0 && (
        <div className="text-xs p-2 rounded mb-3" style={{ background: 'color-mix(in srgb, var(--color-success) 10%, transparent)', color: 'var(--text-secondary)' }} data-testid="reuse-summary-card">
          复利 (真实回执)：本事项已采用知识 <b style={{ color: 'var(--color-success)' }}>{reuseSummary.adoptions_total}</b> 次
          （近 30 天 {reuseSummary.adoptions_30d} · 涉及 {reuseSummary.distinct_knowledge} 个知识条目）
          —— 计数来自 adoption 回执，非估算值
        </div>
      )}
      {items.length === 0 ? (
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无知识 (SK-04 publish 后出现)</div>
      ) : (
        <div className="space-y-3">
          {items.map(k => {
            const receipt = receipts[k.id];
            return (
              <div key={k.id} className="p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</span>
                  <Badge color={k.status === 'published' ? 'green' : k.status === 'draft' ? 'yellow' : k.status === 'deprecated' ? 'gray' : 'red'}>{k.status}</Badge>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{k.kind} · rev {k.revision}</span>
                </div>
                <div className="text-xs font-mono mb-2" style={{ color: 'var(--text-muted)' }}>
                  {k.id} · content_hash: {k.content_hash?.slice(0, 12) ?? '-'}…
                  {k.review_at && ` · 复查: ${k.review_at.slice(0, 10)}`}
                </div>
                {/* 前提 (SK-04 必填 ≥1) + 反例 */}
                {k.prerequisites && k.prerequisites.length > 0 && (
                  <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    前提: {k.prerequisites.join('; ')}
                  </div>
                )}
                {k.counter_examples && k.counter_examples.length > 0 && (
                  <div className="text-xs mt-1" style={{ color: 'var(--color-warning)' }}>
                    反例: {k.counter_examples.join('; ')}
                  </div>
                )}
                {/* 复用记录 (C12 R16.5: 只数 adoptions, derived_from 不计) */}
                {receipt && (
                  <div className="text-xs mt-2 p-2 rounded" style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)' }}>
                    采用: total={receipt.total}
                    {Object.keys(receipt.by_decision || {}).length > 0 && (
                      <> · 决策 {JSON.stringify(receipt.by_decision)}</>
                    )}
                    {Object.keys(receipt.by_outcome || {}).length > 0 && (
                      <> · 结果 {JSON.stringify(receipt.by_outcome)}</>
                    )}
                    · 近 30 天 {receipt.recent_30d}
                  </div>
                )}
                {/* body 摘要 (Markdown 渲染) */}
                {k.body && (
                  <details className="mt-2">
                    <summary className="text-xs cursor-pointer" style={{ color: 'var(--text-muted)' }}>查看 body</summary>
                    <div
                      className="text-xs mt-1 p-2 rounded prose-sm"
                      style={{ background: 'var(--bg-muted)', color: 'var(--text-primary)' }}
                      dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(k.body.slice(0, 500)) }}
                    />
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
