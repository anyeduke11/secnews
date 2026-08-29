/**
 * SentinelJudgePage — 哨兵终端 · 判断层判读台 (V2 设计稿 judge-desk 屏)
 *
 * 信息架构: 三层工作流的判断层 — 筛选、分析、关联。
 *  - 待判读队列: 今日热点按评分降序, 判读 → 深读 / 归档 → 收藏
 *  - 右栏: 本周信号 (分类趋势 bars) / 质量门禁 24h / 知识管线 (KL 生命周期计数)
 *
 * 数据源: /api/hotspots (24h) · /api/trends (168h) · /api/quality/summary · /api/knowledge/items
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { CATEGORIES, HotspotItem } from '../../types';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';
import './sentinel.css';

interface TrendPoint {
  label: string;
  hours_ago: number;
  total: number;
  ai: number;
  ai_security: number;
  security: number;
  finance: number;
  startup: number;
  bid: number;
  github: number;
  tech: number;
}

interface QualityGateStat {
  pass: number;
  total: number;
  avg_deduction: number;
}

interface KnowledgeItemLite {
  id: string;
  title: string;
  lifecycle: string;
}

const SIGNAL_DEFS: { key: keyof TrendPoint; label: string; color: string }[] = [
  { key: 'security', label: '网络安全', color: 'var(--sn-cat-sec)' },
  { key: 'ai_security', label: 'AI 安全', color: 'var(--sn-cat-ai)' },
  { key: 'ai', label: 'AI', color: 'var(--sn-cat-ai)' },
  { key: 'github', label: 'GitHub', color: 'var(--sn-cat-git)' },
  { key: 'tech', label: '技术圈', color: 'var(--sn-cat-tech)' },
  { key: 'finance', label: '金融', color: 'var(--sn-cat-fin)' },
  { key: 'bid', label: '招标', color: 'var(--sn-cat-bid)' },
  { key: 'startup', label: '创投', color: 'var(--sn-cat-vc)' },
];

const LIFECYCLE_ORDER = ['kl:raw', 'kl:refine', 'kl:link', 'kl:structure', 'kl:publish'];

function labelOf(category: string): string {
  return CATEGORIES.find(c => c.id === category)?.label ?? category;
}

function tagColorOf(category: string): string {
  switch (category) {
    case 'ai': case 'ai_security': return 'var(--sn-cat-ai)';
    case 'security': return 'var(--sn-cat-sec)';
    case 'finance': return 'var(--sn-cat-fin)';
    case 'startup': return 'var(--sn-cat-vc)';
    case 'bid': return 'var(--sn-cat-bid)';
    case 'github': return 'var(--sn-cat-git)';
    case 'tech': return 'var(--sn-cat-tech)';
    default: return 'var(--sn-cat-ai)';
  }
}

function relTime(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

function heatCells(score: number): boolean[] {
  const n = Math.max(0, Math.min(5, Math.round(score / 20)));
  return [1, 2, 3, 4, 5].map(i => i <= n);
}

export function SentinelJudgePage() {
  const navigate = useNavigate();

  const [items, setItems] = useState<HotspotItem[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [quality, setQuality] = useState<Record<string, QualityGateStat> | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeItemLite[]>([]);
  const [loading, setLoading] = useState(true);
  const [archived, setArchived] = useState<Record<string, 'ok' | 'fail'>>({});
  const [settled, setSettled] = useState<{ ingested: number; rejected: number } | null>(null);

  const reloadPipe = usePipeReloadOnSse();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [hp, tr, qs, ki] = await Promise.all([
        fetch('/api/hotspots?category=all&time_range=24h&limit=15').then(r => r.ok ? r.json() : { items: [], total: 0 }),
        fetch('/api/trends?hours=168').then(r => r.ok ? r.json() : { trends: [] }).catch(() => ({ trends: [] })),
        fetch('/api/quality/summary').then(r => r.ok ? r.json() : null).catch(() => null),
        fetch('/api/knowledge/items?limit=200').then(r => r.ok ? r.json() : { items: [] }).catch(() => ({ items: [] })),
      ]);
      // 队列按评分降序 (判读优先级 = 信号强度)
      setItems([...(hp.items || [])].sort((a, b) => (b.score ?? b.quality_score ?? 0) - (a.score ?? a.quality_score ?? 0)));
      setTrends(tr.trends || []);
      setQuality(qs?.summary ?? null);
      setKnowledge(ki.items || []);
      setSettled({ ingested: hp.total ?? 0, rejected: 0 });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useSSE({ onEvent: () => { reloadPipe(); load(); } });

  // 本周信号 bars: 168h 各分类汇总
  const signals = useMemo(() => {
    const sums = new Map<string, number>();
    for (const t of trends) {
      for (const d of SIGNAL_DEFS) {
        sums.set(d.key, (sums.get(d.key) ?? 0) + Number(t[d.key] ?? 0));
      }
    }
    const rows = SIGNAL_DEFS
      .map(d => ({ ...d, count: sums.get(d.key) ?? 0 }))
      .filter(d => d.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
    const max = Math.max(1, ...rows.map(r => r.count));
    return { rows, max };
  }, [trends]);

  // KL 管线分布
  const pipeline = useMemo(() => {
    const counts = new Map<string, number>();
    for (const k of knowledge) {
      const stage = LIFECYCLE_ORDER.includes(k.lifecycle) ? k.lifecycle : '其他';
      counts.set(stage, (counts.get(stage) ?? 0) + 1);
    }
    return LIFECYCLE_ORDER.map(stage => ({ stage, count: counts.get(stage) ?? 0 }));
  }, [knowledge]);

  // 质量门禁汇总
  const qs = useMemo(() => {
    if (!quality) return null;
    const gates = Object.entries(quality);
    if (gates.length === 0) return null;
    let checked = 0;
    let weakest: [string, QualityGateStat] = gates[0];
    let weakestRate = Number.POSITIVE_INFINITY;
    for (const g of gates) {
      checked = Math.max(checked, g[1].total);
      const rate = g[1].total > 0 ? g[1].pass / g[1].total : 1;
      if (rate < weakestRate) { weakestRate = rate; weakest = g; }
    }
    return { checked, weakest, totalGates: gates.length };
  }, [quality]);

  const archive = useCallback(async (item: HotspotItem) => {
    try {
      const r = await fetch('/api/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hotspot_id: item.id,
          category: item.category,
          title: item.title,
          source: item.source,
          url: item.url,
        }),
      });
      setArchived(prev => ({ ...prev, [item.id]: r.ok ? 'ok' : 'fail' }));
    } catch {
      setArchived(prev => ({ ...prev, [item.id]: 'fail' }));
    }
  }, []);

  return (
    <SentinelShell layer="judge" ingested={settled?.ingested ?? null}>
      <section className="scr judge-scr" aria-label="判断层 · 判读台">
        <div className="jd-headrow">
          <div>
            <h2 className="jd-title">判断层</h2>
            <p className="jd-sub">今日 {settled?.ingested ?? '…'} 篇到值得记住的几条：筛选、分析、关联都在这里完成。</p>
          </div>
          <div className="jd-settle num">
            今日收录 <b>{settled?.ingested ?? '…'}</b>
            <span className="sep" />门禁 {qs?.totalGates ?? '--'} 道
            <span className="sep" />队列 {items.length} 条
          </div>
        </div>

        <div className="jd-grid">
          <div className="jd-main">
            <span className="jd-kick">PENDING QUEUE · 待判读队列</span>
            {loading ? (
              <div className="story-top" aria-busy="true">
                <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" />
              </div>
            ) : items.length === 0 ? (
              <div className="empty-panel">
                <div className="empty-ring" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                </div>
                <h3>今日队列已清空</h3>
                <p>暂无待判读条目。采集管线每 5 分钟运行，可回资料层浏览最新快讯。</p>
                <button className="empty-cta" onClick={() => navigate('/')}>返回资料层</button>
              </div>
            ) : (
              <div className="jd-tablewrap">
                <table className="jd-tbl">
                  <thead>
                    <tr>
                      <th scope="col">评分</th><th scope="col">标题</th><th scope="col">频道</th>
                      <th scope="col">来源</th><th scope="col">时间</th><th scope="col">热度</th><th scope="col">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map(item => {
                      const score = Math.round(item.score ?? item.quality_score ?? 0);
                      const isP0 = score >= 80 && (item.category === 'security' || item.category === 'ai_security');
                      return (
                        <tr key={item.id} className={isP0 ? 'jd-p0' : undefined}>
                          <td className="jd-id num">{score}</td>
                          <td>
                            <p className="jd-rowtitle">
                              {isP0 && <span className="jd-badge">高危</span>}
                              <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                            </p>
                          </td>
                          <td><span className="ftag" style={{ color: tagColorOf(item.category) }}>{labelOf(item.category)}</span></td>
                          <td className="jd-src">{item.source}</td>
                          <td className="jd-when num">{relTime(item.ingested_at ?? item.published_at)}</td>
                          <td>
                            <span className="mini-heat" aria-hidden="true">
                              {heatCells(score).map((on, i) => <b key={i} className={on ? 'on' : undefined} />)}
                            </span>
                          </td>
                          <td className="jd-ops">
                            <button type="button" className="jd-op" onClick={() => navigate(`/deep/hotspot/${item.id}`)}>判读</button>
                            {' '}
                            <button type="button" className="jd-op" onClick={() => archive(item)}>
                              {archived[item.id] === 'ok' ? '已归档' : '归档'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="jd-note">提示：「判读」进入四节深度分析；「归档」将条目存入收藏，进入知识管线。队列随采集自动刷新。</p>
          </div>

          <aside className="jd-side">
            <div className="jd-mod">
              <h3>本周信号<small>SIGNALS · 7D</small></h3>
              {signals.rows.length === 0 ? (
                <p className="jd-note">暂无趋势数据</p>
              ) : (
                <ul className="jd-bars">
                  {signals.rows.map(s => (
                    <li key={s.key}>
                      <span className="bk">{s.label}</span>
                      <span className="btrack"><i className="bfill" style={{ width: `${(s.count / signals.max) * 100}%`, background: s.color }} /></span>
                      <span className="bv num">{s.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="jd-mod">
              <h3>质量门禁<small>GATEKEEPER · 24H</small></h3>
              {qs ? (
                <ul className="jd-bars">
                  <li><span className="bk">检查条目</span><span className="btrack"><i className="bfill" style={{ width: '100%' }} /></span><span className="bv num">{qs.checked}</span></li>
                  <li>
                    <span className="bk">最弱 {qs.weakest[0]}</span>
                    <span className="btrack"><i className="bfill" style={{ width: `${Math.round((qs.weakest[1].pass / Math.max(1, qs.weakest[1].total)) * 100)}%`, background: 'var(--sn-amber)' }} /></span>
                    <span className="bv num">{Math.round((qs.weakest[1].pass / Math.max(1, qs.weakest[1].total)) * 100)}%</span>
                  </li>
                </ul>
              ) : (
                <p className="jd-note">暂无门禁数据</p>
              )}
              <a className="rail-link" href="/quality/rejection" onClick={e => { e.preventDefault(); navigate('/quality/rejection'); }}>查看质量拒绝流 →</a>
            </div>

            <div className="jd-mod">
              <h3>知识管线<small>KL PIPELINE</small></h3>
              <ul className="jd-bars">
                {pipeline.map(p => (
                  <li key={p.stage}>
                    <span className="bk">{p.stage.replace('kl:', '')}</span>
                    <span className="btrack"><i className="bfill" style={{ width: `${Math.min(100, (p.count / Math.max(1, Math.max(...pipeline.map(x => x.count)))) * 100)}%`, background: 'var(--sn-mint)' }} /></span>
                    <span className="bv num">{p.count}</span>
                  </li>
                ))}
              </ul>
              <a className="rail-link" href="/judge/graph" onClick={e => { e.preventDefault(); navigate('/judge/graph'); }}>打开知识图谱 →</a>
            </div>
          </aside>
        </div>
      </section>
    </SentinelShell>
  );
}
