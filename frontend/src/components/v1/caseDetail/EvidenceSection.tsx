/**
 * EvidenceSection — D1.2 证据材料区块 (立项携带 v1_case_materials 绑定, SK-02 evidence 输入端)
 * (B5 续拆: 自 CaseDetail.tsx 原样搬运, DOM/class/section 锚点逐字不变)
 */
import type { CaseEvidenceMaterial } from '../../../api/v1';

export function EvidenceSection({ materials }: { materials: CaseEvidenceMaterial[] }) {
  return (
    <div id="section-evidence" className="p-4 rounded-lg border" style={{ background: 'var(--bg-card)', borderColor: 'var(--line)' }}>
      <h3 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        证据 (Evidence){' '}
        <span className="text-xs font-normal" style={{ color: 'var(--text-muted)' }}>
          {materials.length} 条 · 来自立项信号 · SK-02 evidence 输入
        </span>
      </h3>
      {(materials ?? []).length === 0 ? (
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
          暂无证据材料 (从资料层信号立项时自动携带)
        </div>
      ) : (
        <div className="space-y-2">
          {(materials ?? []).map(m => (
            <div key={m.id} className="flex items-start justify-between gap-3 p-3 rounded border" style={{ borderColor: 'var(--line)' }}>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">
                  {m.url ? (
                    <a href={m.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-primary)' }}>{m.title}</a>
                  ) : (
                    <span style={{ color: 'var(--text-primary)' }}>{m.title}</span>
                  )}
                </div>
                <div className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>
                  {m.id} · hash: {m.content_hash?.slice(0, 12) ?? '-'}…{m.signal_id ? ` · 信号 ${m.signal_id.slice(0, 8)}…` : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
