/**
 * graphModel — 知识图谱页 (/knowledge/graph) 的契约类型 / 常量 / 纯函数 (B5 从 SentinelGraphPage 抽出)
 *
 * 只放无 React 依赖的内容: 布局 (placeNodes) 与统计 (computeGraphStats) 都是确定性纯函数,
 * 同一份数据永远得到同一组坐标与同一份文案 → 无抖动、可测。
 * 数据面口径与无障碍契约见容器 SentinelGraphPage.tsx 文件头; 展示区块见 Graph*.tsx。
 */

export interface GraphNode {
  id: string;
  label: string;
  domain: string | null;
  count: number;
  wiki: string;
  type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  type: string;
}

/** /api/knowledge/concepts 单行 — 图谱节点本身不带 entity_type / updated_at, 需按 slug 关联 */
export interface ConceptMeta {
  slug: string;
  entity_type: string | null;
  updated_at: string | null;
  local_wiki_ref: string | null;
  external_id: string | null;
  external_ref: string | null;
  source_items: string[];
}

/** /api/knowledge/concepts/{slug} — 比列表多一个已解析标题的 items */
export interface ConceptDetail extends ConceptMeta {
  title: string;
  domain: string | null;
  items: { id: string; title: string; domain: string | null }[];
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** 画布尺寸: 与 V2 原型 kg-graphsvg 同 viewBox 口径, 坐标即视图坐标 */
export const VIEW_W = 760;
export const VIEW_H = 520;
const CENTER_X = VIEW_W / 2;
const CENTER_Y = 258;
const R_INNER = 62;
const R_OUTER = 224;
/** 扇区排布用的无理数步长 (0.618…), 保证同域节点分散且不随渲染次数漂移 */
const GOLDEN = 0.6180339887498949;
const WEEK_DAYS = 7;
const MONTH_DAYS = 30;
export const INDEX_LIMIT = 60;

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

export function domainOf(node: { domain: string | null }): string {
  return node.domain && DOMAIN_DEFS[node.domain] ? node.domain : 'unknown';
}

export function domainLabel(domain: string): string {
  return DOMAIN_DEFS[domain]?.label ?? domain;
}

export function domainFill(domain: string): string {
  return DOMAIN_DEFS[domain]?.fill ?? 'kg-f-mute';
}

/** API 下发的引用只有 http(s) 才能当 href: 本仓安全审计把 javascript: href 列为待修项 */
export function safeHttpUrl(value?: string | null): string | null {
  if (!value) return null;
  return /^https?:\/\/\S+$/i.test(value.trim()) ? value.trim() : null;
}

/** 实测 entity_type 只有 generic / cve; red 专属漏洞语境, 故只认 cve */
export function isVulnEntity(entityType?: string | null): boolean {
  return entityType === 'cve';
}

function daysSince(iso?: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86400000);
}

export function shortDate(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 截断标题: 中文按字符, 避免 SVG 文字溢出扇区 */
export function ellipsis(text: string, max = 10): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export interface PlacedNode extends GraphNode {
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
export function placeNodes(nodes: GraphNode[], degOf: Map<string, number>, vulnIds: Set<string>): PlacedNode[] {
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

/** 度分布: 每条边给两端各记 1 (图谱口径, 不区分方向) */
export function degreeOfEdges(edges: GraphEdge[]): Map<string, number> {
  const map = new Map<string, number>();
  for (const e of edges) {
    map.set(e.source, (map.get(e.source) ?? 0) + 1);
    map.set(e.target, (map.get(e.target) ?? 0) + 1);
  }
  return map;
}

export interface GraphStats {
  domains: [string, number][];
  nodeTypes: [string, number][];
  edgeTypes: [string, number][];
  isolated: number;
  cve: number;
  refs: number;
  recent: number;
  month: number;
  oldestDays: number | null;
  maxDomain: number;
}

/** 域分布 / 类型分布 / 边分布 — 全部由当次响应实测统计, 供文字替代与说明行复用 */
export function computeGraphStats(graph: GraphPayload, metaBySlug: Map<string, ConceptMeta>): GraphStats {
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
}

/** SVG 的等价文字描述 (role="img" + aria-label): 数量/类型/域分布/孤立/漏洞实体全部实测口径 */
export function buildSvgLabel(graph: GraphPayload, stats: GraphStats): string {
  const dist = stats.domains.map(([d, c]) => `${domainLabel(d)} ${c}`).join(' · ');
  const total = graph.nodes.length || 1;
  const edgeTotal = graph.edges.length || 1;
  const types = stats.nodeTypes.map(([t, c]) => `${t} ${c}/${total}`).join(' · ');
  const edgeDist = stats.edgeTypes.map(([t, c]) => `${t} ${c}/${edgeTotal}`).join(' · ');
  return `知识图谱：${graph.nodes.length} 个概念节点、${graph.edges.length} 条关联边。节点类型 ${types || '无'}。域分布 ${dist || '无'}。边类型 ${edgeDist || '无'}。${stats.isolated} 个节点暂无关联边${stats.cve > 0 ? `，其中 ${stats.cve} 个为漏洞实体节点` : ''}。等价的节点选择操作见下方「节点索引」列表。`;
}
