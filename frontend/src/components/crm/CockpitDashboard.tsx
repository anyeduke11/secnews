/**
 * CockpitDashboard — 座舱复盘 (PRD US-3)
 *
 * 8 KPI 卡 + 3 手写 SVG 图表 (月度营收 / 区域分布 / 商机漏斗)。
 * 数据源 GET /api/crm/stats; 图表配色走 CSS 变量, 不硬编码色值。
 */
import { useEffect, useState } from 'react';
import { crmFetch } from '../../lib/crm';
import type { CockpitStats } from '../../types/crm';

function fmtMoney(n: number | null): string {
  if (n === null) return '—';
  return `¥${Math.round(n).toLocaleString('zh-CN')}`;
}
function fmtPct(n: number | null): string {
  return n === null ? '—' : `${(n * 100).toFixed(1)}%`;
}

const KPI_CARDS: { key: keyof CockpitStats['kpi']; label: string; render: (v: number | null) => string }[] = [
  { key: 'annual_revenue', label: '年度营收', render: v => fmtMoney(v) },
  { key: 'gross_margin', label: '毛利率', render: v => fmtPct(v) },
  { key: 'customers_total', label: '客户总数', render: v => String(v ?? 0) },
  { key: 'repeat_rate', label: '复购率', render: v => fmtPct(v) },
  { key: 'in_pipeline', label: '在管商机', render: v => String(v ?? 0) },
  { key: 'win_rate', label: '赢单率', render: v => fmtPct(v) },
  { key: 'avg_deal_size', label: '平均单额', render: v => fmtMoney(v) },
  { key: 'nps', label: 'NPS', render: v => (v === null ? '—' : String(v)) },
];

/** 月度营收柱状图 — 近 12 月, 空月画基线 */
function MonthlyRevenueChart({ data }: { data: CockpitStats['charts']['monthly_revenue'] }) {
  const byMonth = new Map(data.map(d => [d.month, d.revenue]));
  const months: string[] = [];
  const now = new Date();
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  const max = Math.max(1, ...months.map(m => byMonth.get(m) ?? 0));
  const W = 560;
  const H = 140;
  const barW = W / months.length;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="近 12 月月度营收柱状图">
      <line x1="0" y1={H - 16} x2={W} y2={H - 16} stroke="var(--border-color)" strokeWidth="1" />
      {months.map((m, i) => {
        const rev = byMonth.get(m) ?? 0;
        const h = Math.round(((H - 30) * rev) / max);
        return (
          <g key={m}>
            <rect
              x={i * barW + barW * 0.18}
              y={H - 16 - h}
              width={barW * 0.64}
              height={h}
              fill="var(--accent)"
              opacity={rev > 0 ? 0.85 : 0.12}
            >
              <title>{`${m}: ${fmtMoney(rev)}`}</title>
            </rect>
            <text
              x={i * barW + barW / 2}
              y={H - 4}
              textAnchor="middle"
              fontSize="8"
              fill="var(--text-muted)"
            >
              {m.slice(5)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** 区域分布横向条形图 (本年已赢单金额) */
function RegionChart({ data }: { data: CockpitStats['charts']['region_distribution'] }) {
  if (data.length === 0) {
    return <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>本年暂无区域营收数据</p>;
  }
  const max = Math.max(...data.map(d => d.amount), 1);
  const W = 560;
  const rowH = 22;
  const H = data.length * rowH + 6;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="区域营收分布条形图">
      {data.map((d, i) => (
        <g key={d.region}>
          <text x="0" y={i * rowH + 14} fontSize="10" fill="var(--text-secondary)">{d.region}</text>
          <rect
            x="52"
            y={i * rowH + 5}
            width={Math.max(2, ((W - 130) * d.amount) / max)}
            height={12}
            fill="var(--accent)"
            opacity="0.8"
          >
            <title>{`${d.region}: ${fmtMoney(d.amount)}`}</title>
          </rect>
          <text x={W} y={i * rowH + 14} textAnchor="end" fontSize="9" fill="var(--text-muted)">
            {fmtMoney(d.amount)}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** 商机漏斗 — 四个活跃阶段在管数量/金额 */
function FunnelChart({ data }: { data: CockpitStats['charts']['funnel'] }) {
  const max = Math.max(...data.map(d => d.count), 1);
  const W = 560;
  const rowH = 26;
  const H = data.length * rowH + 4;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="商机阶段漏斗图">
      {data.map((d, i) => {
        const ratio = d.count / max;
        const w = Math.max(24, W * 0.72 * ratio);
        const x = (W - w) / 2;
        return (
          <g key={d.stage}>
            <rect x={x} y={i * rowH + 3} width={w} height={rowH - 8} fill="var(--accent)" opacity={0.85 - i * 0.15}>
              <title>{`${d.stage}: ${d.count} 单 / ${fmtMoney(d.amount)}`}</title>
            </rect>
            <text x={W / 2} y={i * rowH + rowH / 2 + 1} textAnchor="middle" fontSize="10" fill="var(--text-on-light)" fontWeight="600">
              {d.stage} · {d.count} 单
            </text>
            <text x={W} y={i * rowH + rowH / 2 + 1} textAnchor="end" fontSize="9" fill="var(--text-muted)">
              {fmtMoney(d.amount)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function CockpitDashboard() {
  const [stats, setStats] = useState<CockpitStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    crmFetch<CockpitStats>('/api/crm/stats')
      .then(s => { if (!cancelled) setStats(s); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return <p className="text-sm py-8 text-center" style={{ color: 'var(--color-error)' }}>座舱数据加载失败: {error}</p>;
  }
  if (!stats) {
    return <p className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>正在加载座舱…</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {KPI_CARDS.map(({ key, label, render }) => (
          <div key={key} className="border rounded p-3" style={{ borderColor: 'var(--border-color)' }}>
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{label}</p>
            <p className="font-mono text-lg font-bold tabular-nums mt-0.5" style={{ color: 'var(--text-primary)' }} data-testid={`kpi-${key}`}>
              {render(stats.kpi[key])}
            </p>
          </div>
        ))}
      </div>

      <div className="border rounded p-3" style={{ borderColor: 'var(--border-color)' }}>
        <h3 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>月度营收 (近 12 月)</h3>
        <MonthlyRevenueChart data={stats.charts.monthly_revenue} />
      </div>
      <div className="grid md:grid-cols-2 gap-2">
        <div className="border rounded p-3" style={{ borderColor: 'var(--border-color)' }}>
          <h3 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>区域分布 (本年赢单)</h3>
          <RegionChart data={stats.charts.region_distribution} />
        </div>
        <div className="border rounded p-3" style={{ borderColor: 'var(--border-color)' }}>
          <h3 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>商机漏斗</h3>
          <FunnelChart data={stats.charts.funnel} />
        </div>
      </div>
    </div>
  );
}
