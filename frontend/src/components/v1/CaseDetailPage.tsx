/**
 * CaseDetailPage — /cases/:caseId 判断层深链接页 (v0.8.5 C2, spec = docs/v0.8.5/V0.8.5_PLAN.md §5)
 *
 * 壳: SentinelShell layer=judge (三层唯一壳, 无 AppNav); 内容: CaseDetail (V1Prototype 提取)。
 * URL 真相源: caseId = 路径参数; ?section= 可选定位 (judgments/actions/artifacts/knowledge
 * → 对应区块滚动锚点, spec §6.3)。
 * 数据: getCase 单点拉取; 失败显 unavailable, 不伪造数据。
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { SentinelShell } from '../sentinel/SentinelShell';
import { CaseDetail } from './CaseDetail';
import { getCase } from '../../api/v1';
import type { Case } from '../../domain/v1_0';

const SECTION_ANCHORS: Record<string, string> = {
  judgment: 'section-judgments', judgments: 'section-judgments',
  action: 'section-actions', actions: 'section-actions',
  run: 'section-actions', runs: 'section-actions',
  artifact: 'section-actions', artifacts: 'section-actions',
  knowledge: 'section-knowledge',
};

export function CaseDetailPage() {
  const { caseId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [case_, setCase_] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!caseId) return;
    setError(null);
    setCase_(null);
    getCase(caseId)
      .then((r) => { if (!cancelled) setCase_((r as { item: Case }).item ?? (r as unknown as Case)); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [caseId]);

  // ?section= 定位: case 加载完成后滚动到对应区块 (CaseDetail 首帧渲染完再锚定)
  useEffect(() => {
    if (!case_) return;
    const anchor = SECTION_ANCHORS[searchParams.get('section') ?? ''];
    if (anchor) {
      requestAnimationFrame(() => {
        document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  }, [case_, searchParams]);

  return (
    <SentinelShell layer="judge">
      <main className="sentinel-main">
        <div className="max-w-6xl mx-auto p-6" data-testid="case-detail-page">
          {!caseId && (
            <div className="p-3 rounded border text-sm" style={{ borderColor: 'var(--sn-line)', color: 'var(--sn-ink-3)' }}>
              URL 缺少 case id (用法: /cases/&#123;caseId&#125;)
            </div>
          )}
          {caseId && error && (
            <div className="p-3 rounded border text-sm" style={{ borderColor: 'var(--sn-red)', color: 'var(--sn-red)' }}>
              事项加载失败 (unavailable): {error}
            </div>
          )}
          {caseId && !error && !case_ && (
            <div className="p-3 rounded border text-sm" style={{ borderColor: 'var(--sn-line)', color: 'var(--sn-ink-3)' }}>
              加载中…
            </div>
          )}
          {case_ && <CaseDetail case_={case_} onBack={() => navigate('/judge')} />}
        </div>
      </main>
    </SentinelShell>
  );
}
