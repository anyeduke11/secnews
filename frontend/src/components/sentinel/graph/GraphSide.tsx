/**
 * GraphSide — 右栏三面板 (kg-side): 选中节点详情 / 关联条目 / 本周增长 (B5 从 SentinelGraphPage 抽出)
 *
 * 纯展示: 详情数据 (detail) 与派生量由容器传入; 动作 (隐藏节点 / 站内跳转) 走回调。
 * 增长口径按 concepts.updated_at 实测标注, 后端无 created_at / 无历史快照 → 不伪造时间序列。
 */
import {
  domainLabel, domainOf, shortDate,
  type ConceptDetail, type ConceptMeta, type GraphNode, type GraphStats,
} from './graphModel';

export function GraphSide({ selected, selectedMeta, detail, detailError, selectedType, isVuln, selectedDeg, wikiHref, neighbors, metaCount, stats, nodeCount, edgeCount, onHideNode, onNavigate }: {
  selected: GraphNode | null;
  selectedMeta?: ConceptMeta;
  detail: ConceptDetail | null;
  detailError: string | null;
  selectedType: string;
  isVuln: boolean;
  selectedDeg: number;
  wikiHref: string | null;
  neighbors: string[];
  metaCount: number;
  stats: GraphStats;
  nodeCount: number;
  edgeCount: number;
  onHideNode: (id: string) => void;
  onNavigate: (to: string) => void;
}) {
  return (
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
              <button type="button" className="kg-op" onClick={() => onHideNode(selected.id)}>
                在图谱中隐藏
              </button>
              <button type="button" className="kg-op" onClick={() => onNavigate(`/knowledge?concept=${encodeURIComponent(selected.id)}`)}>
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
                    <a href={href} onClick={e => { e.preventDefault(); onNavigate(href); }}>
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
        {metaCount === 0 ? (
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
              图谱规模 <b>{nodeCount}</b> 节点 / <b>{edgeCount}</b> 边 · 概念引用条目合计 <b>{stats.refs}</b>
              {stats.oldestDays != null ? ` · 最久未更新 ${stats.oldestDays} 天` : ''}
            </p>
            <p className={`kg-caveat mono${stats.recent === 0 ? ' kg-caveat-warn' : ''}`}>
              后端 concepts/graph 均无 created_at 与历史快照，上述按 updated_at 统计；
              {stats.recent === 0 ? ' 近 7 天无概念更新，故本周增长为 0（非渲染缺失）。' : ' 数值随每轮编译变化。'}
            </p>
            <a className="rail-link" href="/knowledge/compile" onClick={e => { e.preventDefault(); onNavigate('/knowledge/compile'); }}>
              查看知识编译状态 →
            </a>
          </>
        )}
      </section>

      <p className="kg-side-end mono">数据源 /api/knowledge/graph · /api/knowledge/concepts</p>
    </aside>
  );
}
