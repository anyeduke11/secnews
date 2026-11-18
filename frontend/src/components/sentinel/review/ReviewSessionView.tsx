/**
 * ReviewSessionView — 复习栈弹层「会话」视图 (B5 从 ReviewOverlay 抽出)
 *
 * 翻卡 (正面=标题+类型+领域徽标, 背面=摘要 excerpt+SM-2 参数), 空格翻面,
 * 1/3/5 评分进下一张; 结束汇总页: 已评数 / 评分分布 / 每张可撤销。
 * 取数与写操作 (listDueReviews / submitReviewGrade / undoReviewGrade) 原样搬运,
 * 请求顺序与次数不变; DOM / class / aria 与拆分前逐字一致。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { listDueReviews, submitReviewGrade, undoReviewGrade } from '../../../api/action';
import {
  RV_GRADES, isEditableTarget, rvTitle,
  type RvRow, type SessionResult,
} from './reviewModel';

export function ReviewSessionView({ onDataChanged }: { onDataChanged: () => void }) {
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
    listDueReviews<RvRow>(50, { enrich: true })
      .then(d => { if (!dead) setRows(Array.isArray(d.items) ? d.items : []); })
      .catch(() => { if (!dead) setRows([]); });
    return () => { dead = true; };
  }, []);

  const cur = rows && idx < rows.length ? rows[idx] : null;
  const phase = rows === null ? 'loading' : cur ? 'drill' : 'summary';

  const grade = useCallback((g: number) => {
    if (!cur || saving) return;
    setSaving(true);
    submitReviewGrade<{ item?: RvRow }>(
      cur.entity_type,
      cur.entity_id,
      g,
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
    undoReviewGrade(r.row.entity_type, r.row.entity_id)
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
