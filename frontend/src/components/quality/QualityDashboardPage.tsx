/**
 * QualityDashboardPage — 校对室 (/quality, Phase 4 DEV-0183)
 *
 * 定位: 资料菜单「质量校对」全貌页 — 门禁统计 + 信息过滤规则 + 拒绝样本入口。
 * 数据 (全部真实 API):
 *  - GET /api/quality/summary   — 各门禁 24h 统计 (pass/total/avg_deduction)
 *  - GET /api/info-filter/rules — 信息过滤规则清单 (v0.8 P1 已实现, 非占位)
 * 子标签: 「拒绝样本」即原 QualityRejectionPage (路由 /quality/rejection 重定向到
 *  /quality?tab=rejection, 保持旧深链兼容)。
 * 注意: info_filter 为 feature gate (默认开); gate 关闭时规则区降级为
 *  「功能未开启」空态, 不报错。
 */
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getJSON } from '../../lib/api';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import QualityRejectionPage from '../QualityRejectionPage';
import '../shared/editorial/pages.css';

interface GateStat {
  pass?: number;
  total?: number;
  avg_deduction?: number;
}

interface QualitySummaryShape {
  summary?: Record<string, GateStat>;
}

interface FilterRule {
  id?: number;
  rule_type?: string;
  match_kind?: string;
  match_value?: string;
  note?: string;
  enabled?: boolean;
}

type TabKey = 'overview' | 'rejection';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '校对总览' },
  { key: 'rejection', label: '拒绝样本' },
];

export function QualityDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: TabKey = searchParams.get('tab') === 'rejection' ? 'rejection' : 'overview';

  const [summary, setSummary] = useState<QualitySummaryShape | null>(null);
  const [rules, setRules] = useState<FilterRule[] | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== 'overview') return;
    let alive = true;
    getJSON<QualitySummaryShape>('/api/quality/summary').then(d => { if (alive) setSummary(d); }).catch(() => { /* 显示 … */ });
    getJSON<{ rules?: FilterRule[] }>('/api/info-filter/rules')
      .then(d => { if (alive) setRules(d.rules ?? []); })
      .catch(e => {
        if (!alive) return;
        setRules([]);
        setRulesError(e instanceof Error ? e.message : String(e));
      });
    return () => { alive = false; };
  }, [tab]);

  function switchTab(next: TabKey) {
    setSearchParams(next === 'rejection' ? { tab: 'rejection' } : {}, { replace: true });
  }

  const gates = summary?.summary ? Object.entries(summary.summary) : [];

  return (
      <div className="ed-wrap">
        <header className="ed-head">
          <span className="ed-kicker">PROOFROOM</span>
          <h1 className="ed-h1">校对室</h1>
          <p className="ed-sub">收录质量的全貌: 门禁通过情况、信息过滤规则、以及被校对拦下的样本。</p>
        </header>

        <div className="ed-tabs" role="tablist" aria-label="校对室分区">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              className={`ed-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => switchTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'rejection' ? (
          <QualityRejectionPage />
        ) : (
          <>
            <div className="ed-sechead">
              <span>门禁统计 (24h)</span>
              <span className="ed-note">/api/quality/summary</span>
            </div>
            {gates.length === 0 ? (
              <EmptyState title="暂无门禁统计" description="等待下一轮质量检查写入数据, 或确认后端运行中。" />
            ) : (
              <div className="ed-grid">
                {gates.map(([name, g]) => {
                  const total = g.total ?? 0;
                  const pass = g.pass ?? 0;
                  const rate = total > 0 ? Math.round((pass / total) * 100) : null;
                  return (
                    <div className="ed-card" key={name}>
                      <span className="t">{name}</span>
                      <span className="v">
                        {rate === null ? '…' : `${rate}%`}
                        <small>{pass}/{total} 通过</small>
                      </span>
                      <span className="d">平均扣分 {typeof g.avg_deduction === 'number' ? g.avg_deduction.toFixed(2) : '--'}</span>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="ed-sechead">
              <span>信息过滤规则</span>
              <span className="ed-note">/api/info-filter/rules</span>
            </div>
            {rules === null ? (
              <EmptyState title="规则加载中…" />
            ) : rulesError ? (
              <EmptyState title="规则接口不可用" description={`${rulesError} — info_filter 为 feature gate, 关闭时此区不生效。`} />
            ) : rules.length === 0 ? (
              <div style={{ marginBottom: 8 }}>
                <Stamp color="info" variant="hollow">尚无规则 · 全部放行</Stamp>
              </div>
            ) : (
              <table className="ed-table" aria-label="信息过滤规则">
                <thead>
                  <tr>
                    <th>类型</th>
                    <th>匹配</th>
                    <th>值</th>
                    <th>状态</th>
                    <th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.slice(0, 50).map((r, i) => (
                    <tr key={r.id ?? i}>
                      <td className="mono">{r.rule_type ?? '--'}</td>
                      <td className="mono">{r.match_kind ?? '--'}</td>
                      <td>{r.match_value ?? '--'}</td>
                      <td className="mono">{r.enabled === false ? '停用' : '启用'}</td>
                      <td>{r.note ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
  );
}
