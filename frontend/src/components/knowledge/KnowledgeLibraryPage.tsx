/**
 * KnowledgeLibraryPage — 编目室 (/knowledge/library, Phase 4 建, C1 接真实数据 DEV-0189)
 *
 * 定位: 知识条目的编目清单 = `knowledge_items` 表的镜像视图 (wiki-first 单一事实源, 不建平行表)。
 * 数据 (全部真实 API):
 *  - GET /api/knowledge/items?domain&topic&type&difficulty&limit&offset — 编目行 + total
 *    (后端口径注意: total 仅按 domain 计数, 其余筛选不影响 total — 页脚如实标注「域内」)
 *  - GET /api/knowledge/topics?domain= — 主题下拉选项 (随领域联动)
 * 筛选枚举与 KnowledgeFilters 同源 (DOMAINS/TYPES/DIFFICULTIES, 单一来源导入)。
 * 不做关键词搜索: 端点未暴露 keyword; 全文检索由 /search 与 /api/wiki/search 承载 (DD-4)。
 */
import { useCallback, useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';
import { Stamp } from '../shared/editorial/Stamp';
import { EmptyState } from '../EmptyState';
import { DIFFICULTIES, DOMAINS, TYPES } from '../KnowledgeFilters';
import '../shared/editorial/pages.css';

interface LibraryItem {
  id: string;
  title: string;
  source: string;
  domain: string | null;
  type: string | null;
  difficulty: string | null;
  mastery: number | null;
  ingested_at: string;
}

interface LibraryFilters {
  domain: string;
  topic: string;
  type: string;
  difficulty: string;
}

const EMPTY_FILTERS: LibraryFilters = { domain: '', topic: '', type: '', difficulty: '' };
const PAGE_SIZE = 50;

export function KnowledgeLibraryPage() {
  const [filters, setFilters] = useState<LibraryFilters>(EMPTY_FILTERS);
  const [topics, setTopics] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((f: LibraryFilters, p: number) => {
    const params = new URLSearchParams();
    if (f.domain) params.set('domain', f.domain);
    if (f.topic) params.set('topic', f.topic);
    if (f.type) params.set('type', f.type);
    if (f.difficulty) params.set('difficulty', f.difficulty);
    params.set('limit', String(PAGE_SIZE));
    params.set('offset', String((p - 1) * PAGE_SIZE));
    return getJSON<{ items?: LibraryItem[]; total?: number }>(`/api/knowledge/items?${params.toString()}`);
  }, []);

  useEffect(() => {
    let alive = true;
    setError(null);
    load(filters, page)
      .then(d => {
        if (!alive) return;
        setItems(d.items ?? []);
        setTotal(d.total ?? 0);
      })
      .catch(e => {
        if (!alive) return;
        setItems([]);
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => { alive = false; };
  }, [filters, page, load]);

  // 主题下拉随领域联动 (与 KnowledgeFilters 同一端点)
  useEffect(() => {
    if (!filters.domain) {
      setTopics([]);
      return;
    }
    let alive = true;
    getJSON<{ topics?: string[] }>(`/api/knowledge/topics?domain=${encodeURIComponent(filters.domain)}`)
      .then(d => { if (alive) setTopics(d.topics || []); })
      .catch(() => { if (alive) setTopics([]); });
    return () => { alive = false; };
  }, [filters.domain]);

  function setFilter(patch: Partial<LibraryFilters>) {
    setFilters(cur => ({ ...cur, ...patch }));
    setPage(1);
  }

  const hasNext = (items?.length ?? 0) >= PAGE_SIZE;

  return (
      <div className="ed-wrap">
        <header className="ed-head">
          <span className="ed-kicker">CATALOG ROOM</span>
          <h1 className="ed-h1">编目室</h1>
          <p className="ed-sub">知识条目的编目清单 = knowledge_items 镜像 (wiki-first 单一事实源)。领域 / 主题 / 类型 / 难度多维筛选, 掌握度列取 SM-2 库内代理值。</p>
          <div style={{ marginTop: 10 }}>
            <Stamp color="info" variant="hollow">数据源: /api/knowledge/items (真实端点)</Stamp>
          </div>
        </header>

        {/* 筛选条: 枚举与 KnowledgeFilters 同源 */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }} role="group" aria-label="编目筛选">
          <select className="editorial-input" style={{ width: 150 }} aria-label="领域" value={filters.domain} onChange={e => setFilter({ domain: e.target.value, topic: '' })}>
            <option value="">全部领域</option>
            {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <select className="editorial-input" style={{ width: 160 }} aria-label="主题" value={filters.topic} disabled={topics.length === 0} onChange={e => setFilter({ topic: e.target.value })}>
            <option value="">全部主题</option>
            {topics.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="editorial-input" style={{ width: 150 }} aria-label="类型" value={filters.type} onChange={e => setFilter({ type: e.target.value })}>
            <option value="">全部类型</option>
            {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="editorial-input" style={{ width: 150 }} aria-label="难度" value={filters.difficulty} onChange={e => setFilter({ difficulty: e.target.value })}>
            <option value="">全部难度</option>
            {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        <div className="ed-sechead">
          <span>编目清单</span>
          <span className="ed-note">域内 {error ? '…' : total} 条 · 本页 {items?.length ?? 0} 条</span>
        </div>
        <table className="ed-table" aria-label="编目清单">
          <thead>
            <tr>
              <th>条目标识</th>
              <th>标题</th>
              <th>领域</th>
              <th>来源</th>
              <th>类型</th>
              <th>难度</th>
              <th>掌握度</th>
              <th>收录时间</th>
            </tr>
          </thead>
          <tbody>
            {(items ?? []).map(it => (
              <tr key={it.id}>
                <td className="mono">{it.id}</td>
                <td style={{ maxWidth: 360 }}>
                  <span title={it.title}>{it.title}</span>
                </td>
                <td className="mono">{it.domain ?? '--'}</td>
                <td>{it.source}</td>
                <td className="mono">{it.type ?? '--'}</td>
                <td className="mono">{it.difficulty ?? '--'}</td>
                <td className="mono">{it.mastery ?? 0}/5</td>
                <td className="mono">{(it.ingested_at || '').slice(0, 10) || '--'}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {items === null ? (
          <EmptyState title="编目加载中…" />
        ) : error ? (
          <EmptyState
            title="编目清单加载失败"
            description={`${error} — 请确认后端服务运行在 127.0.0.1:8000。`}
          />
        ) : items.length === 0 ? (
          <EmptyState
            title="该筛选条件下暂无编目条目"
            description="条目经采集管线编译后自动入编目; 换个筛选条件或先去知识库导入条目。"
          />
        ) : null}

        {/* 翻页: hasNext 以本页条数判定 (total 为域口径, 不随非 domain 筛选变化 — 如实不装) */}
        {!error && (items?.length ?? 0) > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, paddingTop: 16 }}>
            <button type="button" className="ed-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
            <span className="mono" style={{ fontFamily: 'var(--sn-mono)', fontSize: 11, color: 'var(--sn-ink-3)' }} aria-live="polite">
              第 {page} 页 · 本页 {items?.length ?? 0} 条
            </span>
            <button type="button" className="ed-btn" disabled={!hasNext} onClick={() => setPage(p => p + 1)}>下一页</button>
          </div>
        )}
      </div>
  );
}
