/**
 * SentinelRail — 哨兵终端首页右栏
 *
 * 三个模块 (数据由 SentinelHomePage 注入):
 *  - 源监控: 按累计产出排序的采集源 + 三态状态灯
 *  - 质量门禁 24h: 检查量 / 通过率 / 平均分 / 首要拒绝原因
 *  - 今日行动: 未完成待办 + 跳转入口
 */
import { useNavigate } from 'react-router-dom';

interface SourceHealthRow {
  category: string;
  source_name: string;
  status: 'active' | 'stale' | 'dead' | string;
  total_items?: number;
  last_seen_at?: string | null;
}

interface QualityGateStat {
  pass: number;
  total: number;
  avg_deduction: number;
}

/** /api/quality/summary 真实结构: {summary: {gate: {pass, total, avg_deduction}}} */
interface QualitySummaryRaw {
  summary?: Record<string, QualityGateStat>;
}

interface TodoRow {
  id: number;
  title: string;
  status: string;
}

/** 汇总 24h 门禁统计: 检查量 / 最弱门禁 (通过率最低) 及其扣分 */
function gateStats(q: QualitySummaryRaw | null): { checked: number; weakest: string; rate: number; deduction: number } | null {
  const gates = Object.entries(q?.summary ?? {});
  if (gates.length === 0) return null;
  let checked = 0;
  let weakest = gates[0];
  let weakestRate = Number.POSITIVE_INFINITY;
  for (const g of gates) {
    const stat = g[1];
    checked = Math.max(checked, stat.total);
    const rate = stat.total > 0 ? stat.pass / stat.total : 1;
    if (rate < weakestRate) {
      weakestRate = rate;
      weakest = g;
    }
  }
  const [name, stat] = weakest;
  return {
    checked,
    weakest: name,
    rate: stat.total > 0 ? stat.pass / stat.total : 0,
    deduction: stat.avg_deduction ?? 0,
  };
}

export function SentinelRail({ sources, quality, todos }: {
  sources: SourceHealthRow[];
  quality: QualitySummaryRaw | null;
  todos: TodoRow[];
}) {
  const navigate = useNavigate();
  const qs = gateStats(quality);

  const topSources = [...sources]
    .sort((a, b) => (b.total_items ?? 0) - (a.total_items ?? 0))
    .slice(0, 9);

  return (
    <div>
      {/* 源监控 */}
      <section className="rail-mod">
        <h3>
          源监控
          <span className="rail-note">{sources.length} SOURCES</span>
        </h3>
        <ul className="src-list">
          {topSources.length === 0 && (
            <li className="src-row"><span className="src-name" style={{ color: 'var(--sn-ink-3)' }}>暂无源健康数据</span></li>
          )}
          {topSources.map(s => (
            <li className="src-row" key={`${s.category}-${s.source_name}`}>
              <span className="src-name" title={`${s.category} / ${s.source_name}`}>{s.source_name}</span>
              <span className="src-age">{s.total_items ?? 0} 篇</span>
              <span className={`src-state ${s.status === 'active' ? 'ok' : s.status === 'dead' ? 'dead' : 'retry'}`}>
                <i aria-hidden="true" />
                {s.status === 'active' ? 'OK' : s.status === 'dead' ? '离线' : '重试'}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* 质量门禁 24h */}
      <section className="rail-mod">
        <h3>
          质量门禁 · 24H
          <span className="rail-note">GATES</span>
        </h3>
        <div className="judge-stats">
          <div className="js-cell">
            <div className="k">检查条目</div>
            <div className="v">{qs ? qs.checked : '--'}</div>
          </div>
          <div className="js-cell">
            <div className="k">最弱门禁通过率</div>
            <div className="v">{qs ? `${Math.round(qs.rate * 100)}%` : '--'}</div>
          </div>
          <div className="js-cell">
            <div className="k">平均扣分</div>
            <div className="v">{qs ? qs.deduction.toFixed(2) : '--'}</div>
          </div>
          <div className="js-cell">
            <div className="k">首要瓶颈</div>
            <div className="v" style={{ fontSize: 13 }}>
              {qs ? qs.weakest : '无'}
            </div>
          </div>
        </div>
        <a className="rail-link" href="/quality/rejection" onClick={e => { e.preventDefault(); navigate('/quality/rejection'); }}>
          查看质量拒绝流
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </a>
      </section>

      {/* 今日行动 */}
      <section className="rail-mod">
        <h3>
          今日行动
          <span className="rail-note">{todos.length} OPEN</span>
        </h3>
        <ul className="act-list">
          {todos.length === 0 && (
            <li className="act-row" style={{ color: 'var(--sn-ink-3)' }}>暂无待办事项</li>
          )}
          {todos.map(t => (
            <li className="act-row" key={t.id}>
              <span className="act-box" aria-hidden="true" />
              <span style={{ minWidth: 0 }}>{t.title}</span>
            </li>
          ))}
        </ul>
        <a className="rail-link" href="/todos" onClick={e => { e.preventDefault(); navigate('/todos'); }}>
          打开行动清单
          <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </a>
      </section>
    </div>
  );
}
