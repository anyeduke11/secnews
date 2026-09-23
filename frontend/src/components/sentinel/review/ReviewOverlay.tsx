/**
 * ReviewOverlay — 复习栈页内全屏弹层 (2026-09-21 复习栈能力丰富设计稿 §4.2)
 *
 * 单弹层三视图, 页内 state 切换, 零新增路由:
 *  - session 会话视图: 翻卡 (正面=标题+类型+领域徽标, 背面=摘要 excerpt+SM-2 参数),
 *    空格翻面, 1/3/5 评分进下一张; 结束汇总页: 已评数 / 评分分布 / 每张可撤销。
 *  - data 数据视图: 7 日到期预报柱状 / 复习历史流 / 保留率 30d / 评分分布 / 在册+暂停计数。
 *  - manage 管理视图: 全部卡片表格 (暂停/恢复/删除) + 搜索加卡
 *    (GET /api/search?sources=hotspot,knowledge → POST /api/reviews/{type}/{id},
 *    type 按 search 来源映射 hotspot→hotspot, knowledge→knowledge_item)。
 *
 * 视觉: 沿用 sentinel 设计语言, ac-rv-* 命名空间 (sentinel-action.css);
 * 网络调用: 组件内 lib/api (getJSON/postJSON/apiFetch), 与 SentinelActionPage 同款。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, getJSON, postJSON } from '../../../lib/api';
import '../sentinel-action.css';

export type RvView = 'session' | 'data' | 'manage';

const RV_TABS: { key: RvView; label: string }[] = [
  { key: 'session', label: '会话' },
  { key: 'data', label: '数据' },
  { key: 'manage', label: '管理' },
];

/** 面板同款三档自评 (grade 1/3/5) */
const RV_GRADES = [
  { grade: 1, label: '忘光' },
  { grade: 3, label: '模糊' },
  { grade: 5, label: '记得牢' },
] as const;

/** search 来源 → 复习卡 entity_type 映射 */
function sourceToReviewType(t: string): string {
  return t === 'knowledge' ? 'knowledge_item' : 'hotspot';
}

function rvTitle(row: { title?: string | null; entity_id: string }): string {
  return row.title || row.entity_id;
}

function fmtDay(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '--'
    : `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
}

/* ---------------------------------------------------------------------
 * 接口响应类型 (与 backend/api/{reviews,reviews_manage,search}.py 对齐)
 * ------------------------------------------------------------------- */
interface RvRow {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
  suspended?: number;
  title?: string | null;
  url?: string | null;
  category?: string | null;
  excerpt?: string | null;
}

interface ForecastItem { date: string; count: number }

interface HistoryItem {
  id: number;
  entity_type: string;
  entity_id: string;
  grade: number;
  new_interval: number;
  reverted: number;
  created_at: string;
}

interface RvStats {
  total: number;
  due: number;
  avg_easiness: number;
  retention_30d: number | null;
  grade_distribution: Record<string, number>;
  suspended_count: number;
}

interface SearchItem {
  entity_type: string;
  entity_id: string;
  title: string;
  category?: string | null;
}

/** 会话视图评分结果 (汇总页逐张撤销用) */
interface SessionResult {
  key: string;
  row: RvRow;
  grade: number;
  nextInterval: number | null;
}

/** 键盘事件目标守卫: 输入控件内不抢按键 */
function isEditableTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toUpperCase();
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

/* =====================================================================
 * 会话视图 (翻卡)
 * ==================================================================== */
function SessionView({ onDataChanged }: { onDataChanged: () => void }) {
  const [rows, setRows] = useState<RvRow[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [results, setResults] = useState<SessionResult[]>([]);
  const [undone, setUndone] = useState<Record<string, true>>({});
  const [saving, setSaving] = useState(false);
  /** 防止评分 promise 在视图卸载后 setState (测试与快速关闭场景) */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    let dead = false;
    getJSON<{ items?: RvRow[] }>('/api/reviews/due?limit=50&enrich=1')
      .then(d => { if (!dead) setRows(Array.isArray(d.items) ? d.items : []); })
      .catch(() => { if (!dead) setRows([]); });
    return () => { dead = true; };
  }, []);

  const cur = rows && idx < rows.length ? rows[idx] : null;
  const phase = rows === null ? 'loading' : cur ? 'drill' : 'summary';

  const grade = useCallback((g: number) => {
    if (!cur || saving) return;
    setSaving(true);
    postJSON<{ item?: RvRow }>(
      `/api/reviews/${encodeURIComponent(cur.entity_type)}/${encodeURIComponent(cur.entity_id)}/grade`,
      { grade: g },
    )
      .then(data => {
        if (!alive.current) return;
        setResults(rs => [...rs, {
          key: cur.id, row: cur, grade: g,
          nextInterval: typeof data?.item?.interval === 'number' ? data.item.interval : null,
        }]);
        setFlipped(false);
        setIdx(i => i + 1);
        onDataChanged();
      })
      .catch(() => { /* 评分失败: 停在当前卡, 下一按键可重试 */ })
      .finally(() => { if (alive.current) setSaving(false); });
  }, [cur, saving, onDataChanged]);

  const undo = useCallback((r: SessionResult) => {
    if (undone[r.key]) return;
    postJSON(`/api/reviews/${encodeURIComponent(r.row.entity_type)}/${encodeURIComponent(r.row.entity_id)}/undo`, {})
      .then(() => {
        if (!alive.current) return;
        setUndone(u => ({ ...u, [r.key]: true }));
        onDataChanged();
      })
      .catch(() => { /* 409 (log 耗尽等) → 静默保留原状态 */ });
  }, [undone, onDataChanged]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isEditableTarget(e.target)) return;
      if (e.key === ' ') { e.preventDefault(); setFlipped(f => !f); return; }
      if (phase !== 'drill') return;
      const hit = RV_GRADES.find(g => String(g.grade) === e.key);
      if (hit) { e.preventDefault(); grade(hit.grade); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [grade, phase]);

  if (phase === 'loading') {
    return <p className="ac-rv-hint">载入到期队列…</p>;
  }

  if (phase === 'summary') {
    const dist = results.reduce<Record<number, number>>((m, r) => {
      m[r.grade] = (m[r.grade] ?? 0) + 1; return m;
    }, {});
    return (
      <div className="ac-rv-summary">
        <h3 className="ac-rv-sh">本次复习完成</h3>
        <p className="ac-rv-sline">
          已评 <b className="num">{results.length}</b> 张
          {RV_GRADES.map(g => (
            <span key={g.grade} className="num ac-rv-dist">
              {g.label} {dist[g.grade] ?? 0}
            </span>
          ))}
        </p>
        {results.length === 0 && <p className="ac-rv-hint">到期队列为空, 没有需要复习的卡片。</p>}
        <ul className="ac-rv-slist">
          {results.map(r => (
            <li key={r.key}>
              <span className="ac-rv-stitle">{rvTitle(r.row)}</span>
              <span className="ac-rv-smeta num">
                g{r.grade}
                {r.nextInterval != null && <> · 下次 {r.nextInterval} 天后</>}
              </span>
              {undone[r.key]
                ? <span className="ac-rv-sop num is-undone">已撤销</span>
                : (
                  <button type="button" className="ac-rv-opbtn" onClick={() => undo(r)}>
                    撤销
                  </button>
                )}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="ac-rv-drill">
      <p className="ac-rv-progress num">
        {idx + 1} / {rows!.length} · 已评 {results.length}
      </p>
      <article
        className={`ac-rv-card${flipped ? ' is-flipped' : ''}`}
        aria-label={`复习卡：${rvTitle(cur!)}，${flipped ? '背面' : '正面'}`}
      >
        {!flipped ? (
          <div className="ac-rv-face">
            <div className="ac-rv-fmeta">
              <span className="ac-cdeck">{cur!.entity_type.toUpperCase()}</span>
              {cur!.category && <span className="ac-badge">{cur!.category}</span>}
            </div>
            <h3 className="ac-rv-title">{rvTitle(cur!)}</h3>
            <p className="ac-rv-eid num" title={cur!.entity_id}>{cur!.entity_id}</p>
          </div>
        ) : (
          <div className="ac-rv-face">
            <p className="ac-rv-excerpt">{cur!.excerpt || '（该卡无摘要内容，凭标题回忆即可）'}</p>
            <div className="ac-sm2">
              <span>EF <b className="num">{Number(cur!.easiness).toFixed(2)}</b></span>
              <span>间隔 <b className="num">{cur!.interval}d</b></span>
              <span>重复 <b className="num">{cur!.repetitions}</b></span>
              <span>上次 <b className="num">{cur!.last_grade ?? '--'}</b></span>
            </div>
          </div>
        )}
      </article>
      <p className="ac-rv-hint">空格翻面 · 1/3/5 评分进下一张</p>
      <div className="ac-grade">
        {RV_GRADES.map(g => (
          <button
            key={g.grade}
            type="button"
            className="ac-gbtn"
            disabled={saving}
            onClick={() => grade(g.grade)}
          >
            {g.label}
            <span className="g num">g{g.grade}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* =====================================================================
 * 数据视图 (预报 / 历史 / 统计)
 * ==================================================================== */
function DataView() {
  const [forecast, setForecast] = useState<ForecastItem[] | null>(null);
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const [stats, setStats] = useState<RvStats | null>(null);

  useEffect(() => {
    let dead = false;
    Promise.all([
      getJSON<{ items?: ForecastItem[] }>('/api/reviews/forecast?days=7').catch(() => null),
      getJSON<{ items?: HistoryItem[] }>('/api/reviews/history?limit=50').catch(() => null),
      getJSON<{ stats?: RvStats }>('/api/reviews/stats').catch(() => null),
    ]).then(([fc, hs, st]) => {
      if (dead) return;
      setForecast(fc?.items ?? null);
      setHistory(hs?.items ?? null);
      setStats(st?.stats ?? null);
    });
    return () => { dead = true; };
  }, []);

  const maxCount = useMemo(
    () => Math.max(1, ...(forecast ?? []).map(f => f.count)),
    [forecast],
  );
  const distEntries = Object.entries(stats?.grade_distribution ?? {});

  return (
    <div className="ac-rv-data">
      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">7 日到期预报</h4>
        {forecast ? (
          <div className="ac-rv-bars" role="img"
            aria-label={`未来 7 天到期数：${forecast.map(f => `${f.date} ${f.count} 张`).join('，')}`}>
            {forecast.map(f => (
              <div key={f.date} className="ac-rv-barcol" title={`${f.date}：${f.count} 张`}>
                <b className="num">{f.count}</b>
                <i style={{ height: `${Math.round((f.count / maxCount) * 64) + 2}px` }} />
                <span className="num">{f.date.slice(5)}</span>
              </div>
            ))}
          </div>
        ) : <p className="ac-rv-hint">载入中…</p>}
      </section>

      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">保留率与分布</h4>
        <div className="ac-rv-kpis">
          <span>保留率 30d <b className="num">
            {stats ? (stats.retention_30d == null ? '--' : `${Math.round(stats.retention_30d * 100)}%`) : '…'}
          </b></span>
          <span>在册 <b className="num">{stats?.total ?? '--'}</b></span>
          <span>暂停 <b className="num">{stats?.suspended_count ?? '--'}</b></span>
          {distEntries.map(([g, n]) => (
            <span key={g}>g{g} <b className="num">{n}</b></span>
          ))}
        </div>
      </section>

      <section className="ac-rv-block">
        <h4 className="ac-rv-bh">复习历史</h4>
        {history === null ? <p className="ac-rv-hint">载入中…</p> : history.length === 0 ? (
          <p className="ac-rv-hint">还没有评分记录。评分后会在这里留下流水。</p>
        ) : (
          <ul className="ac-rv-hist">
            {history.map(h => (
              <li key={h.id} className={h.reverted ? 'is-reverted' : undefined}>
                <span className="ac-rv-ht num">{fmtDay(h.created_at)}</span>
                <span className="ac-rv-htitle">{h.entity_id}</span>
                <span className="ac-rv-hm num">
                  g{h.grade} · 下次 {h.new_interval}d{h.reverted ? ' · 已撤销' : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* =====================================================================
 * 管理视图 (表格 + 搜索加卡)
 * ==================================================================== */
function ManageView({ onDataChanged }: { onDataChanged: () => void }) {
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
    getJSON<{ items?: RvRow[] }>('/api/reviews/cards?limit=200')
      .then(d => { if (!dead) setCards(Array.isArray(d.items) ? d.items : []); })
      .catch(() => { if (!dead) setCards([]); });
    return () => { dead = true; };
  }, []);

  const doSearch = useCallback(() => {
    const query = q.trim();
    if (!query) { setHits(null); return; }
    setSearching(true);
    getJSON<{ result?: { items?: SearchItem[] } }>(
      `/api/search?q=${encodeURIComponent(query)}&sources=hotspot,knowledge&limit=10`,
    )
      .then(d => { if (alive.current) setHits(d.result?.items ?? []); })
      .catch(() => { if (alive.current) setHits([]); })
      .finally(() => { if (alive.current) setSearching(false); });
  }, [q]);

  const addCard = useCallback((item: SearchItem) => {
    const reviewType = sourceToReviewType(item.entity_type);
    const key = `${reviewType}-${item.entity_id}`;
    if (added[key]) return;
    setAdded(a => ({ ...a, [key]: true }));
    postJSON(`/api/reviews/${encodeURIComponent(reviewType)}/${encodeURIComponent(item.entity_id)}`, {})
      .then(() => { if (alive.current) onDataChanged(); })
      .catch(() => {
        // 失败回滚按钮态 (409/网络等), 允许重试
        if (alive.current) setAdded(a => { const n = { ...a }; delete n[key]; return n; });
      });
  }, [added, onDataChanged]);

  const patchCard = useCallback((row: RvRow, suspended: boolean) => {
    setCards(cs => (cs ?? []).map(c => (c.id === row.id ? { ...c, suspended: suspended ? 1 : 0 } : c)));
    apiFetch(`/api/reviews/${encodeURIComponent(row.entity_type)}/${encodeURIComponent(row.entity_id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ suspended }),
    })
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
    apiFetch(`/api/reviews/${encodeURIComponent(row.entity_type)}/${encodeURIComponent(row.entity_id)}`, { method: 'DELETE' })
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

/* =====================================================================
 * 弹层壳 (三视图切换 + Escape 关闭)
 * ==================================================================== */
export function ReviewOverlay({
  open,
  view,
  onViewChange,
  onClose,
  onDataChanged,
}: {
  open: boolean;
  view: RvView;
  onViewChange: (v: RvView) => void;
  onClose: () => void;
  onDataChanged: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isEditableTarget(e.target)) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ac-rv-backdrop" onClick={onClose}>
      <section
        className="ac-rv-modal"
        role="dialog"
        aria-modal="true"
        aria-label="复习栈工作台"
        onClick={e => e.stopPropagation()}
      >
        <header className="ac-rv-head">
          <div className="ac-rv-tabs" role="tablist" aria-label="复习栈视图">
            {RV_TABS.map(t => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={view === t.key}
                className={`ac-rv-tab${view === t.key ? ' is-active' : ''}`}
                onClick={() => onViewChange(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <button type="button" className="ac-rv-close" aria-label="关闭复习栈" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="ac-rv-body">
          {view === 'session' && <SessionView onDataChanged={onDataChanged} />}
          {view === 'data' && <DataView />}
          {view === 'manage' && <ManageView onDataChanged={onDataChanged} />}
        </div>
      </section>
    </div>
  );
}
