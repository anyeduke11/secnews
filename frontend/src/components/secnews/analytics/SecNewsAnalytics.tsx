/**
 * SecNewsAnalytics — CVE 热力图 + ATT&CK 技术映射 + 合规矩阵三视图
 *
 * S4-3: 嵌入 STIX 子集, 全部前端渲染, 后端静态查询。
 * S4-4: 合规矩阵 (等保 2.0 + GDPR + ISO 27001)。
 */
import { useMemo, useState } from 'react';
import { CveHeatmap } from '../CveHeatmap';
import { AttackNavigator } from '../AttackNavigator';
import { ComplianceMatrix } from '../ComplianceMatrix';
import type { FrameworkOption } from '../FrameworkFilter';

type Tab = 'heatmap' | 'attack' | 'compliance';

const FRAMEWORKS: FrameworkOption[] = [
  { id: 'dengbao', name: '等保 2.0' },
  { id: 'gdpr', name: 'GDPR' },
  { id: 'iso27001', name: 'ISO 27001' },
];

export function SecNewsAnalytics() {
  const [tab, setTab] = useState<Tab>('heatmap');

  const sampleCveIds = useMemo(() => {
    return [] as string[];
  }, []);

  const tabs: { key: Tab; label: string }[] = [
    { key: 'heatmap', label: 'CVE 热力图' },
    { key: 'attack', label: 'ATT&CK 映射' },
    { key: 'compliance', label: '合规矩阵' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 border-b" style={{ borderColor: 'var(--border-color)' }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="px-3 py-1.5 text-sm font-medium transition-colors"
            style={{
              color: tab === t.key ? 'var(--accent)' : 'var(--text-muted)',
              borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'heatmap' && (
        <div className="rounded border p-4" style={{ borderColor: 'var(--border-color)', background: 'var(--bg-primary)' }}>
          <div className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            CVE 时序热力图 (近 12 周)
          </div>
          <div className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
            行 = severity, 列 = week; 颜色深浅 = 该周该 severity CVE 数量
          </div>
          <CveHeatmap />
        </div>
      )}

      {tab === 'attack' && (
        <div className="rounded border p-4" style={{ borderColor: 'var(--border-color)', background: 'var(--bg-primary)' }}>
          <div className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            MITRE ATT&CK 技术映射
          </div>
          <div className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
            基于 CVE → CWE → ATT&CK technique 静态映射 (嵌入 STIX 子集)
          </div>
          <AttackNavigator cveIds={sampleCveIds} />
        </div>
      )}

      {tab === 'compliance' && (
        <div className="rounded border p-4" style={{ borderColor: 'var(--border-color)', background: 'var(--bg-primary)' }}>
          <div className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            合规矩阵 (等保 2.0 + GDPR + ISO 27001)
          </div>
          <div className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
            事件类型 ↔ 合规条款交叉表，点击单元格查看控制项
          </div>
          <ComplianceMatrix frameworks={FRAMEWORKS} />
        </div>
      )}
    </div>
  );
}

