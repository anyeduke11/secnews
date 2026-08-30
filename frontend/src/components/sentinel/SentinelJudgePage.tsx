/**
 * SentinelJudgePage — 哨兵终端 · 判断层判读台 (V2 设计稿 judge-desk 屏)
 *
 * 信息架构: 三层工作流的判断层 — 筛选、分析、关联。
 *  - 待判读队列: 今日热点按评分降序, 判读 → 深读 / 归档 → 收藏
 *  - 右栏: 本周信号 (分类趋势 bars) / 质量门禁 (拦截数 + 拒因分布) /
 *    知识管线 (KL 生命周期计数) / 时段吞吐 (7 天 × 5 时段点阵)
 *  - 屏尾: 168h 收录与沉淀结算行
 *
 * 数据源: /api/hotspots (24h) · /api/trends (168h) · /api/quality/summary · /api/knowledge/items
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { CATEGORIES, HotspotItem } from '../../types';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';
import './sentinel.css';
import './sentinel-judge.css';

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

/** 「需注意」态: 只从条目已有字段推导, 无异常则不渲染徽标 (不伪造判读状态) */
function stateChipOf(item: HotspotItem): string | null {
  if (item.url_check_status === 'mismatch') return '标题待核';
  if (item.is_fallback) return '兜底来源';
  if (item.url_check_status === 'pending') return '来源待校验';
  const flag = item.quality_flags?.[0];
  return flag ?? null;
}

/** 时段吞吐点阵: 5 个时段 × 7 天 (每格 24/5 ≈ 5 小时) */
const HEAT_BANDS = ['00–05', '05–10', '10–15', '15–20', '20–24'];
const HEAT_DAYS = 7;

interface HeatCell {
  band: number;
  day: number;
  count: number;
}

/** 逐小时趋势 → 行优先 (时段为行、天为列, 左＝7 天前) 的强度矩阵 */
function buildHeatMatrix(trends: TrendPoint[]): { cells: HeatCell[]; max: number } {
  const grid: number[][] = HEAT_BANDS.map(() => new Array(HEAT_DAYS).fill(0));
  const now = Date.now();
  for (const t of trends) {
    const hoursAgo = Number(t.hours_ago ?? 0);
    const day = HEAT_DAYS - 1 - Math.floor(hoursAgo / 24);
    if (day < 0 || day >= HEAT_DAYS) continue;
    const hourOfDay = new Date(now - hoursAgo * 3600000).getHours();
    const band = Math.min(HEAT_BANDS.length - 1, Math.floor(hourOfDay / (24 / HEAT_BANDS.length)));
    grid[band][day] += Number(t.total ?? 0);
  }
  const cells: HeatCell[] = [];
  let max = 0;
  grid.forEach((row, band) => row.forEach((count, day) => {
    cells.push({ band, day, count });
    if (count > max) max = count;
  }));
  return { cells, max };
}

/** rail-link 箭头: 与 SentinelRail 同一内联 SVG 语汇 */
function ArrowGlyph() {
  return (
    <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function SentinelJudgePage() {
  const navigate = useNavigate();

  const [items, setItems] = useState<HotspotItem[]>([]);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [quality, setQuality] = useState<Record<string, QualityGateStat> | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeItemLite[]>([]);
  const [loading, setLoading] = useState(true);
  const [archived, setArchived] = useState<Record<string, 'ok' | 'fail'>>({});
  // AI 评测 (POST /api/llm/evaluate) — 迁移自 workbench/AnalyzeView, 逐行独立状态
  const [evalMap, setEvalMap] = useState<Record<string, {
    busy?: boolean;
    score?: number;
    verdict?: string;
    key_points?: string[];
    provider?: string;
    error?: string;
  }>>({});

  const evaluate = useCallback(async (item: HotspotItem) => {
    const content = (item.summary || '').trim() || item.title;
    if (content.length < 10) {
      setEvalMap(m => ({ ...m, [item.id]: { error: '正文不足 10 字, 后端会拒 422' } }));
      return;
    }
    setEvalMap(m => ({ ...m, [item.id]: { busy: true } }));
    try {
      const r = await fetch('/api/llm/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ content, title: item.title }),
      });
      if (!r.ok) {
        setEvalMap(m => ({ ...m, [item.id]: { error: `评测失败 (${r.status})` } }));
        return;
      }
      const d = await r.json();
      // 后端严格模式: 失败返回 ok=False + error, 不静默降级 —— 原样呈现
      if (d.ok === false) {
        setEvalMap(m => ({ ...m, [item.id]: { error: String(d.error || 'LLM 调用失败') } }));
        return;
      }
      setEvalMap(m => ({
        ...m,
        [item.id]: {
          score: d.quality_score,
          verdict: d.verdict,
          key_points: Array.isArray(d.key_points) ? d.key_points.slice(0, 3) : [],
          provider: d.provider,
        },
      }));
    } catch {
      setEvalMap(m => ({ ...m, [item.id]: { error: '评测失败: 网络或后端不可达' } }));
    }
  }, []);
  const [archiving, setArchiving] = useState<Record<string, boolean>>({});
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

  // 质量门禁汇总 — intercepted 按「门禁次数」累计 (同一条目可被多道门禁命中, 非去重条目数)
  const qs = useMemo(() => {
    if (!quality) return null;
    const gates = Object.entries(quality);
    if (gates.length === 0) return null;
    let checked = 0;
    let intercepted = 0;
    let weakest: [string, QualityGateStat] = gates[0];
    let weakestRate = Number.POSITIVE_INFINITY;
    const rows: { name: string; blocked: number; rate: number; tone: number }[] = [];
    for (const [name, g] of gates) {
      checked = Math.max(checked, g.total);
      const blocked = Math.max(0, g.total - g.pass);
      intercepted += blocked;
      const rate = g.total > 0 ? g.pass / g.total : 1;
      if (rate < weakestRate) { weakestRate = rate; weakest = [name, g]; }
      rows.push({ name, blocked, rate, tone: 1 });
    }
    rows.sort((a, b) => b.blocked - a.blocked);
    // 同一 amber 语义色承载层级: 拦截量越高越靠前、越实
    rows.forEach((r, i) => { r.tone = Math.max(0.34, 1 - i * 0.22); });
    return {
      checked, weakest, totalGates: gates.length, intercepted,
      topGates: rows.filter(r => r.blocked > 0).slice(0, 4),
    };
  }, [quality]);

  // 时段吞吐点阵 (7 天 × 5 时段)
  const heat = useMemo(() => buildHeatMatrix(trends), [trends]);

  // 168h 收录与沉淀结算
  const weekTotal = useMemo(() => trends.reduce((s, t) => s + Number(t.total ?? 0), 0), [trends]);
  const published = useMemo(
    () => knowledge.filter(k => k.lifecycle === 'kl:publish').length,
    [knowledge],
  );
  const archivedCount = useMemo(
    () => Object.values(archived).filter(v => v === 'ok').length,
    [archived],
  );

  const archive = useCallback(async (item: HotspotItem) => {
    if (archiving[item.id] || archived[item.id] === 'ok') return;
    setArchiving(prev => ({ ...prev, [item.id]: true }));
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
    } finally {
      setArchiving(prev => ({ ...prev, [item.id]: false }));
    }
  }, [archived, archiving]);

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
            <span className="sep" />门禁 <b>{qs?.totalGates ?? '--'}</b> 道
            <span className="sep" />队列 <b>{items.length}</b> 条
          </div>
        </div>

        <div className="jd-grid">
          <div className="jd-main">
            <span className="jd-kick">PENDING QUEUE · 待判读队列</span>
            {loading ? (
              <div className="jd-skel" aria-busy="true" aria-label="待判读队列加载中">
                {[1, 2, 3, 4, 5].map(i => (
                  <div className="jd-skel-row" key={i}>
                    <div className="skel-line c" /><div className="skel-line w2" />
                    <div className="skel-line c" /><div className="skel-line c" />
                  </div>
                ))}
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
                      const state = stateChipOf(item);
                      const done = archived[item.id];
                      const busy = !!archiving[item.id];
                      const ev = evalMap[item.id];
                      const colSpan = 7;
                      return (
                        <Fragment key={item.id}>
                        <tr className={isP0 ? 'jd-p0' : undefined}>
                          <td className="jd-id">{score}<span className="of">/100</span></td>
                          <td>
                            <p className="jd-rowtitle">
                              {isP0 && <span className="jd-badge">高危</span>}
                              <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
                              {state && <span className="jd-state">{state}</span>}
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
                            <span className="jd-opwrap">
                              <button type="button" className="jd-op is-primary" onClick={() => navigate(`/deep/hotspot/${item.id}`)}>判读</button>
                              <button
                                type="button"
                                className={`jd-op${done === 'ok' ? ' is-done' : done === 'fail' ? ' is-fail' : ''}`}
                                disabled={busy || done === 'ok'}
                                onClick={() => archive(item)}
                              >
                                {busy ? '归档中' : done === 'ok' ? '已归档' : done === 'fail' ? '归档失败' : '归档'}
                              </button>
                              <button
                                type="button"
                                className="jd-op"
                                disabled={!!ev?.busy}
                                aria-label={`AI 评测：${item.title}`}
                                onClick={() => evaluate(item)}
                              >
                                {ev?.busy ? '评测中' : 'AI 评测'}
                              </button>
                            </span>
                          </td>
                        </tr>
                        {ev && !ev.busy && (
                          <tr className="jd-evalrow">
                            <td colSpan={colSpan}>
                              {ev.error ? (
                                <span className="jd-eval err">评测未成功：{ev.error}</span>
                              ) : (
                                <span className="jd-eval">
                                  <b className="num">AI {Math.round(ev.score ?? 0)}</b>
                                  {ev.verdict && <em>{ev.verdict}</em>}
                                  {(ev.key_points?.length ?? 0) > 0 && (
                                    <span className="jd-eval-kps">
                                      {ev.key_points!.map((k, i) => <span className="ftag" key={i}>{k}</span>)}
                                    </span>
                                  )}
                                  {ev.provider && <span className="jd-eval-src num">{ev.provider}</span>}
                                </span>
                              )}
                            </td>
                          </tr>
                        )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <p className="jd-note">提示：「判读」进入四节深度分析；「归档」将条目存入收藏并进入知识管线。队列由采集管线每 5 分钟推进，并有 SSE 事件即时刷新。</p>
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
                <>
                  <div className="jd-gnum"><b>{qs.intercepted}</b><span>次 · 24h 拦截合计</span></div>
                  {qs.topGates.length > 0 ? (
                    <>
                      <div
                        className="jd-dist"
                        role="img"
                        aria-label={`拦截分布：${qs.topGates.map(g => `${g.name} ${g.blocked} 次`).join('，')}`}
                      >
                        {qs.topGates.map(g => (
                          <i key={g.name} style={{ width: `${(g.blocked / Math.max(1, qs.intercepted)) * 100}%`, background: 'var(--sn-amber)', opacity: g.tone }} />
                        ))}
                      </div>
                      <div className="jd-leg">
                        {qs.topGates.map(g => (
                          <span key={g.name}><i style={{ background: 'var(--sn-amber)', opacity: g.tone }} />{g.name} {g.blocked}</span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="jd-note">24h 内各门禁均无拦截</p>
                  )}
                  <ul className="jd-bars">
                    <li><span className="bk">检查条目</span><span className="btrack"><i className="bfill" style={{ width: '100%' }} /></span><span className="bv num">{qs.checked}</span></li>
                    <li>
                      <span className="bk">最弱 {qs.weakest[0]}</span>
                      <span className="btrack"><i className="bfill" style={{ width: `${Math.round((qs.weakest[1].pass / Math.max(1, qs.weakest[1].total)) * 100)}%`, background: 'var(--sn-amber)' }} /></span>
                      <span className="bv num">{Math.round((qs.weakest[1].pass / Math.max(1, qs.weakest[1].total)) * 100)}%</span>
                    </li>
                  </ul>
                  <p className="jd-note">口径：拦截按门禁计，同一条目可被多道门禁命中，故合计可大于检查条目。</p>
                  <p className="jd-mod-foot">
                    <a className="rail-link" href="/quality/rejection" onClick={e => { e.preventDefault(); navigate('/quality/rejection'); }}>
                      查看质量拒绝流<ArrowGlyph />
                    </a>
                  </p>
                </>
              ) : (
                <p className="jd-note">暂无门禁数据</p>
              )}
            </div>

            <div className="jd-mod">
              <h3>知识管线<small>KL PIPELINE</small></h3>
              <ul className="jd-bars">
                {pipeline.map(p => (
                  <li key={p.stage}>
                    <span className="bk">{p.stage.replace('kl:', '')}</span>
                    <span className="btrack"><i className="bfill" style={{ width: `${Math.min(100, (p.count / Math.max(1, Math.max(...pipeline.map(x => x.count)))) * 100)}%` }} /></span>
                    <span className="bv num">{p.count}</span>
                  </li>
                ))}
              </ul>
              <p className="jd-mod-foot">
                <a className="rail-link" href="/judge/graph" onClick={e => { e.preventDefault(); navigate('/judge/graph'); }}>
                  打开知识图谱<ArrowGlyph />
                </a>
              </p>
            </div>

            <div className="jd-mod">
              <h3>时段吞吐<small>THROUGHPUT · 7D</small></h3>
              {heat.max === 0 ? (
                <p className="jd-note">暂无逐小时趋势数据</p>
              ) : (
                <>
                  <div
                    className="jd-heat"
                    role="img"
                    aria-label={`过去 7 天 5 个时段的收录吞吐，峰值 ${heat.max} 篇/时段；横列为天（左＝7 天前，右＝今天），纵行为 5 小时时段`}
                  >
                    {heat.cells.map(c => (
                      <i
                        key={`${c.band}-${c.day}`}
                        className={c.count === 0 ? 'is-zero' : undefined}
                        style={c.count === 0 ? undefined : { opacity: 0.18 + 0.82 * (c.count / heat.max) }}
                      />
                    ))}
                  </div>
                  <div className="jd-weeklab"><span>7 天前</span><span>…</span><span>今天</span></div>
                  <p className="jd-note">色块越亮代表该时段收录吞吐越高（纵行为 00–05 至 20–24 五个时段）。</p>
                </>
              )}
            </div>
          </aside>
        </div>

        <p className="jd-settled">
          过去 168 小时共收录 <b>{weekTotal}</b> 篇，其中 <b>{published}</b> 条已发布为知识节点；
          当前待判读队列 <b>{items.length}</b> 条，本次会话已归档 <b>{archivedCount}</b> 条。
          队列随采集管线自动刷新。
        </p>
      </section>
    </SentinelShell>
  );
}
