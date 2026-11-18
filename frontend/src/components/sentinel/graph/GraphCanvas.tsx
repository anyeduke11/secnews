/**
 * GraphCanvas — 图谱主列 (kg-left): 加载骨架 / 两种空态 / 画布 + 图例 + 分布说明 + 节点索引 (B5 从 SentinelGraphPage 抽出)
 *
 * 画布本体 (SVG 直排或挂入 InfiniteCanvas 的结果) 由容器算好后作为 canvas 传入, 本区块不持有画布状态。
 * 索引列表是 SVG 的无障碍等价操作 (键盘可达), 与图形层同源。
 */
import type { ReactNode } from 'react';
import { domainFill, domainLabel, INDEX_LIMIT, type GraphStats, type PlacedNode } from './graphModel';

export function GraphCanvas({ loading, error, nodeCount, edgeCount, metaCount, stats, domain, index, selectedId, canvas, onPick, onRetry, onNavigate }: {
  loading: boolean;
  error: string | null;
  nodeCount: number;
  edgeCount: number;
  metaCount: number;
  stats: GraphStats;
  domain: string;
  index: PlacedNode[];
  selectedId?: string;
  canvas: ReactNode;
  onPick: (node: PlacedNode) => void;
  onRetry: () => void;
  onNavigate: (to: string) => void;
}) {
  return (
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
          <button className="empty-cta" onClick={onRetry}>重试</button>
        </div>
      ) : nodeCount === 0 ? (
        <div className="empty-panel">
          <div className="empty-ring" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="6" cy="14" r="2.6" stroke="currentColor" strokeWidth="1.4" /><circle cx="14" cy="6" r="2.6" stroke="currentColor" strokeWidth="1.4" /><path d="M7.8 12.2 12.2 7.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
          </div>
          <h3>图谱暂无节点</h3>
          <p>后端 /api/knowledge/graph 返回空集合。条目经编译产出概念后才会出现在这里。</p>
          <button className="empty-cta" onClick={() => onNavigate('/')}>返回资讯首页</button>
        </div>
      ) : (
        <>
          {canvas}

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
            节点类型 {stats.nodeTypes.map(([t, c]) => `${t} ${c}/${nodeCount}`).join(' · ') || '无'}
            <span className="sep" />
            边类型 {stats.edgeTypes.map(([t, c]) => `${t} ${c}/${edgeCount}`).join(' · ') || '无'}（同现关联，当前响应仅此一类）
            <span className="sep" />孤立节点 {stats.isolated}
            <span className="sep" />实体类型 cve {stats.cve} / generic {metaCount - stats.cve}
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
                    className={`kg-index-row${selectedId === n.id ? ' is-sel' : ''}`}
                    aria-pressed={selectedId === n.id}
                    onClick={() => onPick(n)}
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
  );
}
