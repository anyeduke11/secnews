/**
 * RecallKnowledgeSection — D3 SK-05 自动召回区块 (同类经验自动浮现, 采用免手填 · 复利飞轮传动)
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/data-testid 逐字不变; 候选来自 aggregate)
 */
import type { KnowledgeRecallCandidate } from '../../../api/v1';
import { Badge } from './CaseBadge';

interface Props {
  candidates: KnowledgeRecallCandidate[];
  adoptedIds: Set<string>;
  onAdopt: (k: KnowledgeRecallCandidate) => void;
}

export function RecallKnowledgeSection({ candidates, adoptedIds, onAdopt }: Props) {
  if (candidates.length === 0) return null;
  return (
    <div className="p-4 rounded-lg border" style={{ background: 'color-mix(in srgb, var(--color-info) 6%, transparent)', borderColor: 'var(--line)' }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          召回知识 (SK-05 自动){' '}
          <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>
            {candidates.length} 条 · 按本事项文本匹配 · 采用后产生回执
          </span>
        </h3>
      </div>
      <ul className="space-y-2">
        {candidates.map(k => {
          const adopted = adoptedIds.has(k.id);
          return (
            <li key={k.id} className="flex items-start justify-between gap-3 p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{k.title}</div>
                <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                  {k.kind} · {k.reasons.join('；')}
                </div>
              </div>
              {adopted ? (
                <Badge color="green">已采用 ✓</Badge>
              ) : (
                <button
                  type="button"
                  onClick={() => onAdopt(k)}
                  className="text-xs px-2.5 py-1 rounded font-medium focus-ring shrink-0"
                  style={{ background: 'var(--color-success)', color: 'var(--text-on-success, #fff)' }}
                  data-testid="recall-adopt-btn"
                >
                  采用
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
