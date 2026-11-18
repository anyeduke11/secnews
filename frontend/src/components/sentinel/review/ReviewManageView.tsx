/**
 * ReviewManageView — 复习栈弹层「管理」视图 (B5 从 ReviewOverlay 抽出)
 *
 * 全部卡片表格 (暂停/恢复/删除) + 搜索加卡
 * (GET /api/search?sources=hotspot,knowledge → POST /api/reviews/{type}/{id},
 * type 按 search 来源映射 hotspot→hotspot, knowledge→knowledge_item)。
 * 取数与写操作 (listReviewCards / searchAll / createReviewItem / updateReview / deleteReview)
 * 原样搬运, 乐观更新与失败回滚不变; DOM / class / aria 与拆分前逐字一致。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createReviewItem,
  deleteReview,
  listReviewCards,
  searchAll,
  updateReview,
} from '../../../api/action';
import {
  fmtDay, rvTitle, sourceToReviewType,
  type RvRow, type SearchItem,
} from './reviewModel';

export function ReviewManageView({ onDataChanged }: { onDataChanged: () => void }) {
  const [cards, setCards] = useState<RvRow[] | null>(null);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<SearchItem[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [added, setAdded] = useState<Record<string, true>>({});
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    let dead = false;
    listReviewCards<{ items?: RvRow[] }>(200)
      .then(d => { if (!dead) setCards(Array.isArray(d.items) ? d.items : []); })
      .catch(() => { if (!dead) setCards([]); });
    return () => { dead = true; };
  }, []);

  const doSearch = useCallback(() => {
    const query = q.trim();
    if (!query) { setHits(null); return; }
    setSearching(true);
    searchAll<{ result?: { items?: SearchItem[] } }>(query, {
      sources: 'hotspot,knowledge',
      limit: 10,
    })
      .then(d => { if (alive.current) setHits(d.result?.items ?? []); })
      .catch(() => { if (alive.current) setHits([]); })
      .finally(() => { if (alive.current) setSearching(false); });
  }, [q]);

  const addCard = useCallback((item: SearchItem) => {
    const reviewType = sourceToReviewType(item.entity_type);
    const key = `${reviewType}-${item.entity_id}`;
    if (added[key]) return;
    setAdded(a => ({ ...a, [key]: true }));
    createReviewItem(reviewType, item.entity_id)
      .then(() => { if (alive.current) onDataChanged(); })
      .catch(() => {
        // 失败回滚按钮态 (409/网络等), 允许重试
        if (alive.current) setAdded(a => { const n = { ...a }; delete n[key]; return n; });
      });
  }, [added, onDataChanged]);

  const patchCard = useCallback((row: RvRow, suspended: boolean) => {
    setCards(cs => (cs ?? []).map(c => (c.id === row.id ? { ...c, suspended: suspended ? 1 : 0 } : c)));
    updateReview(row.entity_type, row.entity_id, { suspended })
      .then(() => { if (alive.current) onDataChanged(); })
      .catch(() => {
        if (alive.current) {
          setCards(cs => (cs ?? []).map(c => (c.id === row.id ? { ...c, suspended: suspended ? 0 : 1 } : c)));
        }
      });
  }, [onDataChanged]);

  const removeCard = useCallback((row: RvRow) => {
    const prev = cards;
    setCards(cs => (cs ?? []).filter(c => c.id !== row.id));
    deleteReview(row.entity_type, row.entity_id)
      .then(() => { if (alive.current) onDataChanged(); })
      .catch(() => { if (alive.current) setCards(prev); });
  }, [cards, onDataChanged]);

  return (
    <div className="ac-rv-manage">
      <div className="ac-rv-search">
        <input
          type="text"
          value={q}
          placeholder="搜索热点/知识条目，加入复习栈"
          aria-label="搜索加入复习卡"
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); doSearch(); } }}
        />
        <button type="button" className="ac-rv-sbtn" disabled={!q.trim() || searching} onClick={doSearch}>
          {searching ? '搜索中' : '搜索'}
        </button>
      </div>
      {hits && (
        <ul className="ac-rv-hits">
          {hits.length === 0 && <li className="ac-rv-hint">没有匹配的热点/知识条目。</li>}
          {hits.map(h => {
            const reviewType = sourceToReviewType(h.entity_type);
            const key = `${reviewType}-${h.entity_id}`;
            const inStack = (cards ?? []).some(c => c.entity_type === reviewType && c.entity_id === h.entity_id);
            return (
              <li key={key}>
                <span className="ac-rv-hit-t">{h.title}</span>
                <span className="ac-badge">{h.entity_type}</span>
                {inStack
                  ? <span className="ac-rv-sop num is-undone">在册</span>
                  : (
                    <button
                      type="button"
                      className="ac-rv-opbtn"
                      disabled={!!added[key]}
                      onClick={() => addCard(h)}
                    >
                      {added[key] ? '已加入' : '加入复习'}
                    </button>
                  )}
              </li>
            );
          })}
        </ul>
      )}

      {cards === null ? <p className="ac-rv-hint">载入卡片…</p> : cards.length === 0 ? (
        <p className="ac-rv-hint">复习栈还是空的。搜索一条热点或知识条目加入。</p>
      ) : (
        <table className="ac-rv-table">
          <thead>
            <tr><th>卡片</th><th>EF</th><th>间隔</th><th>到期</th><th>状态</th><th><span className="sr-only">操作</span></th></tr>
          </thead>
          <tbody>
            {cards.map(c => (
              <tr key={c.id} className={c.suspended ? 'is-suspended' : undefined}>
                <td className="ac-rv-cell-title">
                  {rvTitle(c)}
                  <span className="ac-rv-eid num">{c.entity_type} · {c.entity_id}</span>
                </td>
                <td className="num">{Number(c.easiness).toFixed(2)}</td>
                <td className="num">{c.interval}d</td>
                <td className="num">{fmtDay(c.due_at)}</td>
                <td className="num">{c.suspended ? '暂停' : '在册'}</td>
                <td className="ac-rv-cell-ops">
                  <button type="button" className="ac-rv-opbtn" onClick={() => patchCard(c, !c.suspended)}>
                    {c.suspended ? '恢复' : '暂停'}
                  </button>
                  <button type="button" className="ac-rv-opbtn is-danger" onClick={() => removeCard(c)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
