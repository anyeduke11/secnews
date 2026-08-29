/**
 * SentinelGraphPage — 哨兵终端 · 判断层知识图谱 (V2 设计稿 knowledge-graph 屏)
 *
 * 信息架构: 判断层第二屏 — 把孤立条目织成概念网。
 *  - 主区: 零依赖手写 SVG 图谱 (确定性域扇区布局, 无 physics 抖动) + 图例 + 分布说明 + 节点索引
 *  - 右栏: 选中节点详情 / 关联条目 / 本周增长
 *
 * 数据面现实 (2026-08-29 实测, 界面按真实口径标注, 不伪造):
 *  - GET /api/knowledge/graph → {nodes:[98], edges:[107]}; 节点 type 恒为 concept,
 *    边 type 恒为 related (graph_builder 由 concepts 同现统计生成), weight 为同现次数
 *  - GET /api/knowledge/concepts → 98 行, 含 entity_type (generic 96 / cve 2) 与 updated_at
 *  - GET /api/knowledge/concepts/{slug} → 追加 items:[{id,title,domain}] (关联条目真名)
 *  - 无 created_at / 无图谱时间序列 → "本周增长" 按 concepts.updated_at 口径并在界面注明
 *  - 服务端 domain 过滤在 ai/general 等域返回 0 (缓存路径), 故筛选一律在客户端做
 *
 * 无障碍: SVG 为一张图 (role="img" + aria-label 描述节点/边数量与分布),
 * 全部图形元素 aria-hidden; 等价操作由「节点索引」文字列表提供 (键盘可达)。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSSE } from '../../hooks/useSSE';
import { SentinelShell, usePipeReloadOnSse } from './SentinelShell';
import './sentinel.css';
import './sentinel-graph.css';

interface GraphNode {
  id: string;
  label: string;
  domain: string | null;
  count: number;
  wiki: string;
  type: string;
}

interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  type: string;
}

/** /api/knowledge/concepts 单行 — 图谱节点本身不带 entity_type / updated_at, 需按 slug 关联 */
interface ConceptMeta {
  slug: string;
  entity_type: string | null;
  updated_at: string | null;
  local_wiki_ref: string | null;
  external_id: string | null;
  external_ref: string | null;
  source_items: string[];
}

/** /api/knowledge/concepts/{slug} — 比列表多一个已解析标题的 items */
interface ConceptDetail extends ConceptMeta {
  title: string;
  domain: string | null;
  items: { id: string; title: string; domain: string | null }[];
}

interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** 画布尺寸: 与 V2 原型 kg-graphsvg 同 viewBox 口径, 坐标即视图坐标 */
const VIEW_W = 760;
const VIEW_H = 520;
const CENTER_X = VIEW_W / 2;
const CENTER_Y = 258;
const R_INNER = 62;
const R_OUTER = 224;
/** 扇区排布用的无理数步长 (0.618…), 保证同域节点分散且不随渲染次数漂移 */
const GOLDEN = 0.6180339887498949;
const WEEK_DAYS = 7;
const MONTH_DAYS = 30;
const INDEX_LIMIT = 60;

/** 域 → 中文标签 + 填充类; 未列出的域走中性类, 不猜颜色 */
const DOMAIN_DEFS: Record<string, { label: string; fill: string }> = {
  security: { label: '网络安全', fill: 'kg-f-sec' },
  ai: { label: 'AI', fill: 'kg-f-ai' },
  ai_security: { label: 'AI 安全', fill: 'kg-f-ai' },
  finance: { label: '金融', fill: 'kg-f-fin' },
  startup: { label: '创投', fill: 'kg-f-vc' },
  dev: { label: '开发工具', fill: 'kg-f-tech' },
  tech: { label: '技术圈', fill: 'kg-f-tech' },
  github: { label: 'GitHub', fill: 'kg-f-git' },
  bid: { label: '招投标', fill: 'kg-f-bid' },
  general: { label: '综合', fill: 'kg-f-mute' },
  business: { label: '商业', fill: 'kg-f-mute' },
  other: { label: '其他', fill: 'kg-f-mute' },
  unknown: { label: '未分类', fill: 'kg-f-mute' },
};

function domainOf(node: { domain: string | null }): string {
  return node.domain && DOMAIN_DEFS[node.domain] ? node.domain : 'unknown';
}

function domainLabel(domain: string): string {
  return DOMAIN_DEFS[domain]?.label ?? domain;
}

function domainFill(domain: string): string {
  return DOMAIN_DEFS[domain]?.fill ?? 'kg-f-mute';
}

/** API 下发的引用只有 http(s) 才能当 href: 本仓安全审计把 javascript: href 列为待修项 */
function safeHttpUrl(value?: string | null): string | null {
  if (!value) return null;
  return /^https?:\/\/\S+$/i.test(value.trim()) ? value.trim() : null;
}

/** 实测 entity_type 只有 generic / cve; red 专属漏洞语境, 故只认 cve */
function isVulnEntity(entityType?: string | null): boolean {
  return entityType === 'cve';
}

function daysSince(iso?: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86400000);
}

function shortDate(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 截断标题: 中文按字符, 避免 SVG 文字溢出扇区 */
function ellipsis(text: string, max = 10): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

interface PlacedNode extends GraphNode {
  x: number;
  y: number;
  r: number;
  deg: number;
  dom: string;
  vuln: boolean;
}

/**
 * 确定性布局: 按域切扇区 (扇区宽度 ∝ 节点数), 域内按 (度, 关联条目数) 降序
 * 由内向外以 √frac 面积分布铺放。同一份数据永远得到同一组坐标 → 无抖动、可测。
 */
function placeNodes(nodes: GraphNode[], degOf: Map<string, number>, vulnIds: Set<string>): PlacedNode[] {
  const byDomain = new Map<string, GraphNode[]>();
  for (const n of nodes) {
    const key = domainOf(n);
    const bucket = byDomain.get(key);
    if (bucket) bucket.push(n);
    else byDomain.set(key, [n]);
  }
  const ordered = [...byDomain.entries()]
    .map(([dom, list]) => ({
      dom,
      list: [...list].sort((a, b) =>
        (degOf.get(b.id) ?? 0) - (degOf.get(a.id) ?? 0)
        || (b.count ?? 0) - (a.count ?? 0)
        || a.id.localeCompare(b.id)),
    }))
    .sort((a, b) => b.list.length - a.list.length || a.dom.localeCompare(b.dom));

  const total = nodes.length || 1;
  const out: PlacedNode[] = [];
  let angle = -Math.PI / 2;
  for (const group of ordered) {
    const span = (Math.PI * 2 * group.list.length) / total;
    group.list.forEach((n, j) => {
      const deg = degOf.get(n.id) ?? 0;
      const frac = (j + 0.5) / group.list.length;
      const radius = R_INNER + (R_OUTER - R_INNER) * Math.sqrt(frac);
      const theta = angle + span * (((j * GOLDEN) % 1) * 0.86 + 0.07);
      out.push({
        ...n,
        dom: group.dom,
        deg,
        vuln: vulnIds.has(n.id),
        r: Math.max(5, Math.min(17, 5 + Math.sqrt(Math.max(0, n.count ?? 0)) * 2 + Math.min(deg, 12) * 0.75)),
        x: Math.round(Math.min(VIEW_W - 46, Math.max(46, CENTER_X + Math.cos(theta) * radius))),
        y: Math.round(Math.min(VIEW_H - 42, Math.max(34, CENTER_Y + Math.sin(theta) * radius * 0.86))),
      });
    });
    angle += span;
  }
  return out;
}

function counterOf<T>(rows: T[], key: (row: T) => string): Map<string, number> {
  const map = new Map<string, number>();
  for (const r of rows) {
    const k = key(r);
    map.set(k, (map.get(k) ?? 0) + 1);
  }
  return map;
}

export function SentinelGraphPage() {
  const navigate = useNavigate();

  const [graph, setGraph] = useState<GraphPayload>({ nodes: [], edges: [] });
  const [metaBySlug, setMetaBySlug] = useState<Map<string, ConceptMeta>>(new Map());
  const [detail, setDetail] = useState<ConceptDetail | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [domain, setDomain] = useState('all');
  const [hidden, setHidden] = useState<string[]>([]);
  const [ingested, setIngested] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailReq = useRef(0);
  const lastSse = useRef(0);

  const reloadPipe = usePipeReloadOnSse();

  const load = useCallback(async () => {
    setError(null);
    try {
      const [g, c, h] = await Promise.all([
        fetch('/api/knowledge/graph', { headers: { Accept: 'application/json' } })
          .then(r => (r.ok ? (r.json() as Promise<GraphPayload>) : Promise.reject(new Error(`图谱请求失败 (${r.status})`)))),
        fetch('/api/knowledge/concepts', { headers: { Accept: 'application/json' } })
          .then(r => (r.ok ? (r.json() as Promise<{ concepts?: ConceptMeta[] }>) : { concepts: [] }))
          .catch(() => ({ concepts: [] as ConceptMeta[] })),
        // 今日收录口径: 只取 total, 给心跳条用
        fetch('/api/hotspots?category=all&time_range=24h&limit=1')
          .then(r => (r.ok ? (r.json() as Promise<{ total?: number }>) : ({ total: undefined } as { total?: number })))
          .catch(() => ({ total: undefined } as { total?: number })),
      ]);
      const nodes: GraphNode[] = Array.isArray(g?.nodes) ? g.nodes : [];
      const edges: GraphEdge[] = Array.isArray(g?.edges) ? g.edges : [];
      setGraph({ nodes, edges });
      const map = new Map<string, ConceptMeta>();
      for (const row of (c.concepts ?? [])) map.set(row.slug, row);
      setMetaBySlug(map);
      setIngested(typeof h.total === 'number' ? h.total : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '图谱数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // SSE: 采集/编译后图谱会变, 30s 节流重拉 (概念图重建成本高, 不逐事件刷新)
  useSSE({
    onEvent: () => {
      reloadPipe();
      const now = Date.now();
      if (now - lastSse.current < 30000) return;
      lastSse.current = now;
      load();
    },
  });

  const pick = useCallback(async (node: GraphNode) => {
    setSelected(node);
    setDetail(null);
    setDetailError(null);
    const token = ++detailReq.current;
    try {
      const r = await fetch(`/api/knowledge/concepts/${encodeURIComponent(node.id)}`, { headers: { Accept: 'application/json' } });
      if (r.status === 404) {
        if (token === detailReq.current) setDetailError('后端无该概念的详情');
        return;
      }
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      if (token === detailReq.current) setDetail(data as ConceptDetail);
    } catch {
      if (token === detailReq.current) setDetailError('关联条目加载失败 — 稍后重试或回判读台查看该概念');
    }
  }, []);

  const degrees = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of graph.edges) {
      map.set(e.source, (map.get(e.source) ?? 0) + 1);
      map.set(e.target, (map.get(e.target) ?? 0) + 1);
    }
    return map;
  }, [graph.edges]);

  /** 实体类型来自 /api/knowledge/concepts (图谱节点本身不带 entity_type) */
  const vulnIds = useMemo(() => {
    const set = new Set<string>();
    for (const m of metaBySlug.values()) {
      if (isVulnEntity(m.entity_type)) set.add(m.slug);
    }
    return set;
  }, [metaBySlug]);

  const placed = useMemo(() => placeNodes(graph.nodes, degrees, vulnIds), [graph.nodes, degrees, vulnIds]);

  const posOf = useMemo(() => {
    const map = new Map<string, PlacedNode>();
    for (const n of placed) map.set(n.id, n);
    return map;
  }, [placed]);

  const hiddenSet = useMemo(() => new Set(hidden), [hidden]);

  /** 域分布 / 类型分布 / 边分布 — 全部由当次响应实测统计, 供文字替代与说明行复用 */
  const stats = useMemo(() => {
    const dom = counterOf(graph.nodes, n => domainOf(n));
    const types = counterOf(graph.nodes, n => n.type || 'unknown');
    const edgeTypes = counterOf(graph.edges, e => e.type || 'unknown');
    const endpoints = new Set<string>();
    for (const e of graph.edges) { endpoints.add(e.source); endpoints.add(e.target); }
    const isolated = graph.nodes.filter(n => !endpoints.has(n.id)).length;
    const cve = [...metaBySlug.values()].filter(m => isVulnEntity(m.entity_type)).length;
    const refs = [...metaBySlug.values()].reduce((sum, m) => sum + (m.source_items?.length ?? 0), 0);
    const recent = [...metaBySlug.values()].filter(m => {
      const d = daysSince(m.updated_at);
      return d != null && d <= WEEK_DAYS;
    }).length;
    const month = [...metaBySlug.values()].filter(m => {
      const d = daysSince(m.updated_at);
      return d != null && d <= MONTH_DAYS;
    }).length;
    const oldest = [...metaBySlug.values()].map(m => daysSince(m.updated_at)).filter((d): d is number => d != null);
    return {
      domains: [...dom.entries()].sort((a, b) => b[1] - a[1]),
      nodeTypes: [...types.entries()].sort((a, b) => b[1] - a[1]),
      edgeTypes: [...edgeTypes.entries()].sort((a, b) => b[1] - a[1]),
      isolated,
      cve,
      refs,
      recent,
      month,
      oldestDays: oldest.length ? Math.max(...oldest) : null,
      maxDomain: dom.size ? Math.max(...dom.values()) : 1,
    };
  }, [graph, metaBySlug]);

  const domainChips = useMemo(
    () => stats.domains.filter(([d]) => d !== 'unknown'),
    [stats.domains],
  );

  const matchOf = useCallback((node: PlacedNode) => domain === 'all' || node.dom === domain, [domain]);

  const rendered = useMemo(() => placed.filter(n => !hiddenSet.has(n.id)), [placed, hiddenSet]);
  const visibleEdges = useMemo(
    () => graph.edges.filter(e => posOf.has(e.source) && posOf.has(e.target) && !hiddenSet.has(e.source) && !hiddenSet.has(e.target)),
    [graph.edges, posOf, hiddenSet],
  );

  const index = useMemo(
    () => [...rendered].sort((a, b) => b.deg - a.deg || b.count - a.count || a.label.localeCompare(b.label, 'zh-CN')),
    [rendered],
  );

  /** 邻接概念: 选中节点的直接关联, 用于详情面板的「相邻」一行 */
  const neighbors = useMemo(() => {
    if (!selected) return [];
    const ids = visibleEdges
      .filter(e => e.source === selected.id || e.target === selected.id)
      .map(e => (e.source === selected.id ? e.target : e.source));
    return [...new Set(ids)].slice(0, 6).map(id => posOf.get(id)?.label ?? id);
  }, [selected, visibleEdges, posOf]);

  const svgLabel = useMemo(() => {
    const dist = stats.domains.map(([d, c]) => `${domainLabel(d)} ${c}`).join(' · ');
    const total = graph.nodes.length || 1;
    const edgeTotal = graph.edges.length || 1;
    const types = stats.nodeTypes.map(([t, c]) => `${t} ${c}/${total}`).join(' · ');
    const edgeDist = stats.edgeTypes.map(([t, c]) => `${t} ${c}/${edgeTotal}`).join(' · ');
    return `知识图谱：${graph.nodes.length} 个概念节点、${graph.edges.length} 条关联边。节点类型 ${types || '无'}。域分布 ${dist || '无'}。边类型 ${edgeDist || '无'}。${stats.isolated} 个节点暂无关联边${stats.cve > 0 ? `，其中 ${stats.cve} 个为漏洞实体节点` : ''}。等价的节点选择操作见下方「节点索引」列表。`;
  }, [graph, stats]);

  const selectedMeta = selected ? metaBySlug.get(selected.id) : undefined;
  const selectedType = detail?.entity_type || selectedMeta?.entity_type || 'generic';
  const isVuln = isVulnEntity(selectedType);
  const wikiHref = safeHttpUrl(detail?.local_wiki_ref ?? selectedMeta?.local_wiki_ref);
  const selectedDeg = selected ? degrees.get(selected.id) ?? 0 : 0;

  return (
    <SentinelShell layer="judge" ingested={ingested}>
      <section className="scr kg-scr" aria-label="判断层 · 知识图谱">
        <div className="kg-headrow">
          <div>
            <h2 className="kg-title">知识图谱</h2>
            <p className="kg-sub">把孤立条目织成网：概念之间的同现关联持续累积，点击节点或索引行看它的来源条目。</p>
          </div>
          <div className="kg-settle num">
            节点 <b>{loading ? '…' : graph.nodes.length}</b>
            <span className="sep" />边 <b>{loading ? '…' : graph.edges.length}</b>
            <span className="sep" />域 <b>{stats.domains.length}</b>
            <span className="sep" />关联引用 <b>{stats.refs}</b>
          </div>
        </div>

        <div className="kg-filters" role="group" aria-label="按知识域过滤节点">
          <button
            type="button"
            className={`kg-chip${domain === 'all' ? ' is-on' : ''}`}
            aria-pressed={domain === 'all'}
            onClick={() => setDomain('all')}
          >
            全部 <span className="num">{graph.nodes.length}</span>
          </button>
          {domainChips.map(([d, c]) => (
            <button
              key={d}
              type="button"
              className={`kg-chip${domain === d ? ' is-on' : ''}`}
              aria-pressed={domain === d}
              onClick={() => setDomain(cur => (cur === d ? 'all' : d))}
            >
              <i className={`kg-dot ${domainFill(d)}`} aria-hidden="true" />{domainLabel(d)} <span className="num">{c}</span>
            </button>
          ))}
          {hidden.length > 0 && (
            <button type="button" className="kg-chip" onClick={() => setHidden([])}>
              显示已隐藏的 {hidden.length} 个
            </button>
          )}
          <button type="button" className="kg-chip kg-chip-nav" onClick={() => navigate('/judge')}>回判读台</button>
        </div>

        <div className="kg-grid">
          <div className="kg-left">
            {loading ? (
              <div className="kg-canvas kg-loading" aria-busy="true">
                <div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" />
              </div>
            ) : error ? (
              <div className="empty-panel">
                <div className="empty-ring" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 5v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                </div>
                <h3>图谱数据加载失败</h3>
                <p>{error} — 请确认后端服务运行在 127.0.0.1:8000。</p>
                <button className="empty-cta" onClick={() => load()}>重试</button>
              </div>
            ) : graph.nodes.length === 0 ? (
              <div className="empty-panel">
                <div className="empty-ring" aria-hidden="true">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="6" cy="14" r="2.6" stroke="currentColor" strokeWidth="1.4" /><circle cx="14" cy="6" r="2.6" stroke="currentColor" strokeWidth="1.4" /><path d="M7.8 12.2 12.2 7.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
                </div>
                <h3>图谱暂无节点</h3>
                <p>后端 /api/knowledge/graph 返回空集合。条目经编译产出概念后才会出现在这里。</p>
                <button className="empty-cta" onClick={() => navigate('/judge')}>返回判读台</button>
              </div>
            ) : (
              <>
                <svg
                  className="kg-graphsvg"
                  viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
                  role="img"
                  aria-label={svgLabel}
                >
                  <g className="kg-layer-edges" aria-hidden="true">
                    {visibleEdges.map((e, i) => {
                      const a = posOf.get(e.source)!;
                      const b = posOf.get(e.target)!;
                      const dim = !(matchOf(a) && matchOf(b));
                      return (
                        <line
                          key={`${e.source}-${e.target}-${i}`}
                          className={`kg-edge${e.weight >= 4 ? ' kg-edge-strong' : ''}${dim ? ' kg-dim' : ''}`}
                          x1={a.x}
                          y1={a.y}
                          x2={b.x}
                          y2={b.y}
                        />
                      );
                    })}
                  </g>
                  <g className="kg-layer-nodes" aria-hidden="true">
                    {rendered.map(n => {
                      const dim = !matchOf(n);
                      const isSel = selected?.id === n.id;
                      const fill = n.vuln ? 'kg-f-vuln' : domainFill(n.dom);
                      const shape = n.vuln
                        ? <polygon className={`kg-shape ${fill}`} points={`${n.x},${n.y - n.r - 1} ${n.x + n.r},${n.y + n.r * 0.8} ${n.x - n.r},${n.y + n.r * 0.8}`} />
                        : n.r >= 11 || n.dom === 'unknown'
                          ? <rect className={`kg-shape ${fill}`} x={n.x - n.r} y={n.y - n.r} width={n.r * 2} height={n.r * 2} rx={2} />
                          : <circle className={`kg-shape ${fill}`} cx={n.x} cy={n.y} r={n.r} />;
                      const showLab = isSel || (!dim && (n.vuln || n.deg >= 4 || n.count >= 3 || n.r >= 11));
                      return (
                        <g
                          key={n.id}
                          className={`kg-node${isSel ? ' is-sel' : ''}`}
                          data-dim={dim ? '1' : '0'}
                          onClick={() => pick(n)}
                        >
                          <title>{`${n.id} · ${n.label}（${domainLabel(n.dom)} · 关联 ${n.deg} 条边 · ${n.count} 条来源条目）`}</title>
                          {isSel && (
                            <>
                              <circle className="kg-sel-halo" cx={n.x} cy={n.y} r={n.r + 11} />
                              <circle className="kg-sel-ring" cx={n.x} cy={n.y} r={n.r + 6} />
                            </>
                          )}
                          {shape}
                          {showLab && (
                            <text className={isSel ? 'kg-lab-code' : 'kg-lab'} x={n.x} y={n.y + n.r + 13} textAnchor="middle">
                              {ellipsis(n.label)}
                            </text>
                          )}
                        </g>
                      );
                    })}
                  </g>
                  <g className="kg-layer-hubs" aria-hidden="true">
                    {index.slice(0, 4).map(n => (
                      <text key={`hub-${n.id}`} className="kg-lab num" x={n.x} y={n.y - n.r - 7} textAnchor="middle">
                        {`deg ${n.deg}`}
                      </text>
                    ))}
                  </g>
                </svg>

                <div className="kg-legend" aria-hidden="true">
                  {stats.cve > 0 && (
                    <span>
                      <svg viewBox="0 0 14 14" width="11" height="11" aria-hidden="true"><path d="M7 2 12.5 12H1.5z" fill="var(--sn-red)" /></svg>
                      漏洞实体 {stats.cve}（取自 concepts.entity_type）
                    </span>
                  )}
                  {stats.domains.slice(0, 7).map(([d, c]) => (
                    <span key={d}><i className={`kg-dot ${domainFill(d)}`} />{domainLabel(d)} {c}</span>
                  ))}
                  <span><i className="kg-glyph kg-glyph-hub" />关联 ≥4 或条目 ≥3 的节点标注名称</span>
                  <span><i className="kg-glyph kg-glyph-ring" />选中态：mint 环 + 1px 虚线晕环</span>
                </div>

                {/* 数据面如实标注: 只统计当次响应, 不假设后端还有别的类型 */}
                <p className="kg-dist mono">
                  节点类型 {stats.nodeTypes.map(([t, c]) => `${t} ${c}/${graph.nodes.length}`).join(' · ') || '无'}
                  <span className="sep" />
                  边类型 {stats.edgeTypes.map(([t, c]) => `${t} ${c}/${graph.edges.length}`).join(' · ') || '无'}（同现关联，当前响应仅此一类）
                  <span className="sep" />孤立节点 {stats.isolated}
                  <span className="sep" />实体类型 cve {stats.cve} / generic {metaBySlug.size - stats.cve}
                </p>

                <div className="kg-indexwrap">
                  <h3 className="kg-index-head">
                    节点索引
                    <span className="kg-index-note num">
                      {domain === 'all' ? '全部域' : domainLabel(domain)} · {index.length} 项 · 按关联度排序
                      {index.length > INDEX_LIMIT ? ` · 仅列前 ${INDEX_LIMIT}` : ''}
                    </span>
                  </h3>
                  <ul className="kg-index">
                    {index.length === 0 && <li className="kg-index-empty">当前筛选下没有节点</li>}
                    {index.slice(0, INDEX_LIMIT).map(n => (
                      <li key={n.id}>
                        <button
                          type="button"
                          className={`kg-index-row${selected?.id === n.id ? ' is-sel' : ''}`}
                          aria-pressed={selected?.id === n.id}
                          onClick={() => pick(n)}
                        >
                          <i className={`kg-dot ${domainFill(n.dom)}`} aria-hidden="true" />
                          <span className="kg-index-name">{n.label}</span>
                          <span className="kg-index-meta num">{domainLabel(n.dom)}</span>
                          <span className="kg-index-meta num">边 {n.deg}</span>
                          <span className="kg-index-meta num">条目 {n.count}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>

          <aside className="kg-side">
            {/* 选中节点详情 */}
            <section className="kg-mod">
              <h3>选中节点详情<span className="kg-mod-note num">DETAIL</span></h3>
              {!selected ? (
                <p className="kg-hint">在图谱或节点索引中选择一个概念，这里会显示它的域、关联度与来源条目。</p>
              ) : (
                <>
                  <h4 className="kg-name">{selected.label}</h4>
                  <span className={`kg-typechip${isVuln ? ' kg-typechip-vuln' : ''}`}>
                    {isVuln && (
                      <svg viewBox="0 0 14 14" width="11" height="11" fill="none" aria-hidden="true" focusable="false">
                        <path d="M7 2 12.5 12H1.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                      </svg>
                    )}
                    {isVuln ? '漏洞实体' : domainLabel(domainOf(selected))}
                  </span>
                  <dl className="kg-facts">
                    <div><dt>标识</dt><dd className="num">{selected.id}</dd></div>
                    <div><dt>节点类型</dt><dd className="num">{selected.type}</dd></div>
                    <div><dt>关联边</dt><dd className="num">{selectedDeg}</dd></div>
                    <div><dt>来源条目</dt><dd className="num">{selected.count}</dd></div>
                    <div><dt>更新时间</dt><dd className="num">{shortDate(detail?.updated_at ?? selectedMeta?.updated_at)}</dd></div>
                    <div><dt>实体类型</dt><dd className="num">{selectedType}</dd></div>
                  </dl>
                  <p className="kg-defn">
                    {neighbors.length > 0
                      ? `直接相邻：${neighbors.join('、')}。`
                      : '该概念当前没有相邻节点，属孤立概念 — 需要更多同现条目才会入网。'}
                  </p>
                  <p className="kg-ref mono">
                    wiki 引用：{wikiHref ? (
                      <a href={wikiHref} target="_blank" rel="noopener noreferrer">{wikiHref}</a>
                    ) : (detail?.local_wiki_ref || selectedMeta?.local_wiki_ref) ? (
                      '非 http(s) 引用，不作为链接'
                    ) : 'local_wiki_ref 为空'}
                  </p>
                  {(detail?.external_ref ?? selectedMeta?.external_ref) && (
                    <p className="kg-ref mono">外部标识：{detail?.external_ref ?? selectedMeta?.external_ref}</p>
                  )}
                  <div className="kg-opsrow">
                    <button type="button" className="kg-op" onClick={() => setHidden(h => (h.includes(selected.id) ? h : [...h, selected.id]))}>
                      在图谱中隐藏
                    </button>
                    <button type="button" className="kg-op" onClick={() => navigate(`/knowledge?concept=${encodeURIComponent(selected.id)}`)}>
                      在知识库中查看
                    </button>
                  </div>
                </>
              )}
            </section>

            {/* 关联条目 */}
            <section className="kg-mod">
              <h3>关联条目<span className="kg-mod-note num">LINKED ITEMS</span></h3>
              {selected && detailError && <p className="kg-hint">{detailError}</p>}
              {!selected ? (
                <p className="kg-hint">{'未选择节点 — 关联条目来自 /api/knowledge/concepts/{slug} 的 items 字段。'}</p>
              ) : detail ? (
                detail.items.length === 0 ? (
                  <p className="kg-hint">该概念的 source_items 为空（例如由安全实体导入的 CVE 节点），后端没有可读的来源条目。</p>
                ) : (
                  <ul className="kg-links">
                    {detail.items.slice(0, 8).map(it => {
                      const href = `/knowledge/deep-read/${encodeURIComponent(it.id)}`;
                      return (
                        <li key={it.id}>
                          <a href={href} onClick={e => { e.preventDefault(); navigate(href); }}>
                            {it.title || '(未命名条目)'}
                          </a>
                          <span className="kg-link-meta num">{it.domain ?? '--'} · {it.id}</span>
                        </li>
                      );
                    })}
                  </ul>
                )
              ) : detailError ? null : (
                <ul className="kg-links">
                  {Array.from({ length: 3 }).map((_, i) => <li key={i} className="skel-line" style={{ width: '86%', height: 11 }} />)}
                </ul>
              )}
            </section>

            {/* 本周增长 */}
            <section className="kg-mod">
              <h3>本周增长<span className="kg-mod-note num">UPDATED ≤7D</span></h3>
              {metaBySlug.size === 0 ? (
                <p className="kg-hint">/api/knowledge/concepts 未返回数据，增长口径暂不可用。</p>
              ) : (
                <>
                  <div className="kg-growth">
                    <div className="kg-gcell">
                      <span className="k">近 7 天更新概念</span>
                      <span className={`v num${stats.recent > 0 ? ' is-up' : ''}`}>{stats.recent}</span>
                    </div>
                    <div className="kg-gcell">
                      <span className="k">近 30 天更新概念</span>
                      <span className="v num">{stats.month}</span>
                    </div>
                  </div>
                  <ul className="kg-bars">
                    {stats.domains.slice(0, 6).map(([d, c]) => (
                      <li key={d}>
                        <span className="bk">{domainLabel(d)}</span>
                        <span className="btrack"><i className="bfill" style={{ width: `${(c / stats.maxDomain) * 100}%` }} /></span>
                        <span className="bv num">{c}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="kg-count">
                    图谱规模 <b>{graph.nodes.length}</b> 节点 / <b>{graph.edges.length}</b> 边 · 概念引用条目合计 <b>{stats.refs}</b>
                    {stats.oldestDays != null ? ` · 最久未更新 ${stats.oldestDays} 天` : ''}
                  </p>
                  <p className={`kg-caveat mono${stats.recent === 0 ? ' kg-caveat-warn' : ''}`}>
                    后端 concepts/graph 均无 created_at 与历史快照，上述按 updated_at 统计；
                    {stats.recent === 0 ? ' 近 7 天无概念更新，故本周增长为 0（非渲染缺失）。' : ' 数值随每轮编译变化。'}
                  </p>
                  <a className="rail-link" href="/knowledge/compile" onClick={e => { e.preventDefault(); navigate('/knowledge/compile'); }}>
                    查看知识编译状态 →
                  </a>
                </>
              )}
            </section>

            <p className="kg-side-end mono">数据源 /api/knowledge/graph · /api/knowledge/concepts</p>
          </aside>
        </div>
      </section>
    </SentinelShell>
  );
}
