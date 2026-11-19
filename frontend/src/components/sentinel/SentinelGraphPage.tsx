/**
 * SentinelGraphPage — 哨兵终端 · 知识菜单图谱 (NAV4 2026-09-13)
 *
 * B5 (2026-11-18) 绞杀者拆分: 原 766 行单文件按区块拆为 graph/ 下 5 个文件
 * (graphModel / GraphFilters / GraphSvg / GraphCanvas / GraphSide), 本文件只保留
 * 状态、取数编排与区块组合; DOM / class / aria 与拆分前逐字一致 (页面测试原样复用)。
 *
 * 信息架构: 知识 — 把孤立条目织成概念网。
 *  - 主区: 零依赖手写 SVG 图谱 (确定性域扇区布局, 无 physics 抖动) + 图例 + 分布说明 + 节点索引
 *  - 右栏: 选中节点详情 / 关联条目 / 本周增长
 *
 * 壳: SentinelShell layer=knowledge (四菜单壳)
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
import { useRealtimeInvalidation } from '../../hooks/realtime';
import { listHotspots } from '../../api/hotspots';
import {
  getKnowledgeConceptDetail,
  getKnowledgeGraph,
  KnowledgeApiError,
  listKnowledgeConcepts,
} from '../../api/knowledge';
import { useAbortGuard } from '../../hooks/useAbortGuard';
import { SentinelShell } from '../../shell/AppShell';
import { usePipeReloadOnSse } from '../../shell/pipe';
import { InfiniteCanvas } from '../shared/editorial/InfiniteCanvas';
import { GraphFilters } from './graph/GraphFilters';
import { GraphSvg } from './graph/GraphSvg';
import { GraphCanvas } from './graph/GraphCanvas';
import { GraphSide } from './graph/GraphSide';
import {
  buildSvgLabel, computeGraphStats, degreeOfEdges, isVulnEntity, placeNodes, safeHttpUrl,
  VIEW_H, VIEW_W,
  type ConceptDetail, type ConceptMeta, type GraphEdge, type GraphNode, type GraphPayload, type PlacedNode,
} from './graph/graphModel';
import './sentinel.css';
import './sentinel-graph.css';

export function SentinelGraphPage() {
  const navigate = useNavigate();

  const [graph, setGraph] = useState<GraphPayload>({ nodes: [], edges: [] });
  const [metaBySlug, setMetaBySlug] = useState<Map<string, ConceptMeta>>(new Map());
  const [detail, setDetail] = useState<ConceptDetail | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [domain, setDomain] = useState('all');
  const [hidden, setHidden] = useState<string[]>([]);
  // Phase 5 (DEV-0184): 画布模式开关 — 同一 SVG 挂入无限画布 (pan/zoom); SVG 直排模式保留为默认降级
  const [canvasMode, setCanvasMode] = useState(false);
  // A4 (DEV-0188): 画布模式 zoom 感知命中补偿 — zoom 量化到 0.1 档, 避免每帧重渲染整页
  const [canvasHitZoom, setCanvasHitZoom] = useState(1);
  const handleCanvasTransform = useCallback((t: { x: number; y: number; zoom: number }) => {
    const q = Math.max(0.1, Math.round(t.zoom * 10) / 10);
    setCanvasHitZoom(prev => (prev === q ? prev : q));
  }, []);
  const [ingested, setIngested] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailReq = useRef(0);
  const dead = useAbortGuard(); // P1-7 竞态守卫: 卸载后不写状态

  const reloadPipe = usePipeReloadOnSse();

  const load = useCallback(async () => {
    setError(null);
    try {
      const [g, c, h] = await Promise.all([
        // apiFetch 非 ok 抛错 (message 经 getApiErrorMessage 友好化; 原实现为「图谱请求失败 (status)」)
        getKnowledgeGraph(),
        listKnowledgeConcepts<ConceptMeta>()
          .catch(() => ({ concepts: [] as ConceptMeta[] })),
        // 今日收录口径: 只取 total, 给心跳条用
        listHotspots({ category: 'all', time_range: '24h', limit: 1 })
          .catch(() => null),
      ]);
      const nodes: GraphNode[] = Array.isArray(g?.nodes) ? g.nodes : [];
      const edges: GraphEdge[] = Array.isArray(g?.edges) ? g.edges : [];
      if (dead.current) return;
      setGraph({ nodes, edges });
      const map = new Map<string, ConceptMeta>();
      for (const row of (c.concepts ?? [])) map.set(row.slug, row);
      setMetaBySlug(map);
      setIngested(h && typeof h.total === 'number' ? h.total : null);
    } catch (e) {
      if (dead.current) return;
      setError(e instanceof Error ? e.message : '图谱数据加载失败');
    } finally {
      if (!dead.current) setLoading(false);
    }
  }, [dead]);

  useEffect(() => { load(); }, [load]);

  // SSE: 采集/编译后图谱都会变, 订阅全量事件 (不设 types 过滤, 语义与原 useSSE 无 types 一致);
  // 心跳条走 usePipeReloadOnSse 的 10s 节流 + mountedReload 优先 (DEV-0167), 图谱 30s 节流重拉
  // (概念图重建成本高, 不逐事件刷新)。经 src/hooks/realtime.ts 统一注册器路由, 全部只读重拉。
  useRealtimeInvalidation([
    { handler: () => reloadPipe() },
    { handler: () => void load(), throttleMs: 30_000 },
  ]);

  const pick = useCallback(async (node: GraphNode) => {
    setSelected(node);
    setDetail(null);
    setDetailError(null);
    const token = ++detailReq.current;
    try {
      const data = await getKnowledgeConceptDetail(node.id);
      if (dead.current) return;
      if (token === detailReq.current) setDetail(data as unknown as ConceptDetail);
    } catch (e) {
      if (dead.current) return;
      if (token === detailReq.current) {
        // apiFetch 统一封装后 404 需经 KnowledgeApiError.status 判别 (原实现读 r.status)
        if (e instanceof KnowledgeApiError && e.status === 404) {
          setDetailError('后端无该概念的详情');
        } else {
          setDetailError('关联条目加载失败 — 稍后重试或回判读台查看该概念');
        }
      }
    }
  }, [dead]);

  const degrees = useMemo(() => degreeOfEdges(graph.edges), [graph.edges]);

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

  const stats = useMemo(() => computeGraphStats(graph, metaBySlug), [graph, metaBySlug]);

  const domainChips = useMemo(
    () => stats.domains.filter(([d]) => d !== 'unknown'),
    [stats.domains],
  );

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

  const svgLabel = useMemo(() => buildSvgLabel(graph, stats), [graph, stats]);

  const selectedMeta = selected ? metaBySlug.get(selected.id) : undefined;
  const selectedType = detail?.entity_type || selectedMeta?.entity_type || 'generic';
  const isVuln = isVulnEntity(selectedType);
  const wikiHref = safeHttpUrl(detail?.local_wiki_ref ?? selectedMeta?.local_wiki_ref);
  const selectedDeg = selected ? degrees.get(selected.id) ?? 0 : 0;

  // Phase 5: 画布模式 — 同一 SVG (固定像素尺寸) 挂入无限画布; 直排模式原样返回
  const svg = (
    <GraphSvg
      rendered={rendered}
      visibleEdges={visibleEdges}
      posOf={posOf}
      index={index}
      domain={domain}
      selectedId={selected?.id}
      svgLabel={svgLabel}
      canvasMode={canvasMode}
      canvasHitZoom={canvasHitZoom}
      onPick={pick}
    />
  );
  const canvasNode = canvasMode ? (
    <InfiniteCanvas
      height={640}
      worldWidth={VIEW_W * 2}
      worldHeight={VIEW_H * 2}
      ariaLabel="知识图谱画布 (拖拽空白平移, 滚轮缩放, 双击重置)"
      onTransformChange={handleCanvasTransform}
    >
      <div style={{ position: 'absolute', left: VIEW_W / 2, top: VIEW_H / 2 }}>{svg}</div>
    </InfiniteCanvas>
  ) : svg;

  const hideNode = useCallback((id: string) => {
    setHidden(h => (h.includes(id) ? h : [...h, id]));
  }, []);

  return (
    <SentinelShell layer="knowledge" ingested={ingested}>
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

        <GraphFilters
          domain={domain}
          domainChips={domainChips}
          total={graph.nodes.length}
          hiddenCount={hidden.length}
          canvasMode={canvasMode}
          onDomainChange={setDomain}
          onShowHidden={() => setHidden([])}
          onToggleCanvas={() => setCanvasMode(c => !c)}
          onNavigate={navigate}
        />

        <div className="kg-grid">
          <GraphCanvas
            loading={loading}
            error={error}
            nodeCount={graph.nodes.length}
            edgeCount={graph.edges.length}
            metaCount={metaBySlug.size}
            stats={stats}
            domain={domain}
            index={index}
            selectedId={selected?.id}
            canvas={canvasNode}
            onPick={pick}
            onRetry={() => load()}
            onNavigate={navigate}
          />

          <GraphSide
            selected={selected}
            selectedMeta={selectedMeta}
            detail={detail}
            detailError={detailError}
            selectedType={selectedType}
            isVuln={isVuln}
            selectedDeg={selectedDeg}
            wikiHref={wikiHref}
            neighbors={neighbors}
            metaCount={metaBySlug.size}
            stats={stats}
            nodeCount={graph.nodes.length}
            edgeCount={graph.edges.length}
            onHideNode={hideNode}
            onNavigate={navigate}
          />
        </div>
      </section>
    </SentinelShell>
  );
}
