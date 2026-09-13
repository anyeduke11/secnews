import { useState } from 'react';

/**
 * ComplianceEmpty — MP-1 DEV-0217 占位组件
 *
 * 合规视图 (view=compliance) 当前 backend 无合规实体种子:
 * - security_entities.entity_type='compliance' 0 行
 * - _load_compliance_nodes() 返空
 * - _load_compliance_edges() 硬编码 []
 *
 * 留 TODO 给后续 MP (例如 MP-4 合规子任务) 灌入数据; 当前展示清晰的占位文案,
 * 避免硬编码"暂无数据"导致的"图谱坏了"误判。
 */
export function ComplianceEmpty() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="card-base flex flex-col items-center justify-center text-center"
      style={{ minHeight: '300px', padding: '2rem', color: 'var(--text-muted)' }}
      data-testid="compliance-empty"
    >
      <div className="text-2xl mb-3" aria-hidden="true">
        ▢
      </div>
      <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
        合规实体待补
      </p>
      <p className="text-xs mb-4" style={{ maxWidth: '32rem' }}>
        MP-1 范围内未实现合规视图数据; 请使用 attack / cve / full 视图浏览图谱。
      </p>
      <button
        type="button"
        className="text-[10px] underline"
        style={{ color: 'var(--text-muted)' }}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? '收起' : '技术细节'}
      </button>
      {expanded && (
        <div
          className="mt-3 text-left text-[10px] leading-relaxed"
          style={{ maxWidth: '36rem', color: 'var(--text-muted)' }}
        >
          <p>当前状态:</p>
          <ul className="list-disc list-inside mt-1 mb-2">
            <li>security_entities.entity_type='compliance' → 0 行</li>
            <li>_load_compliance_nodes() 返空</li>
            <li>_load_compliance_edges() 硬编码 []</li>
          </ul>
          <p>TODO (留 MP-4 合规子任务): 灌入等保/数安法/网安法/个保法/GDPR 等实体与边。</p>
        </div>
      )}
    </div>
  );
}

export default ComplianceEmpty;
