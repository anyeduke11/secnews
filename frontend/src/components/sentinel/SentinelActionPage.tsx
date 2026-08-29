/**
 * SentinelActionPage — 哨兵终端 · 行动层「今日行动」(V2 设计稿 ACTION FLOOR 屏)
 *
 * 信息架构: 三层工作流的行动层 — 计划、学习、输出。三栏布局契约 ac-grid:
 *  - 复习栈   ← SM-2 间隔重复 (可评分: POST /api/reviews/{type}/{id}/grade)
 *  - 待办清单 ← todos        (可勾选/新增: PATCH · POST /api/todos)
 *  - 判读待办 ← planning_actions (可推进: PUT /api/kl/planning-actions/{id}/status)
 *
 * 本屏要点: planning_actions 历史上 100% pending、无 UI 完成入口,
 * 这里是「推进行动队列」首次成为一等公民 → 全部写操作走乐观更新 + 失败回滚,
 * 不做只读展示。复习卡片仅有 entity_type/entity_id (接口无标题字段), 如实渲染。
 *
 * 数据源 (全部真实 API, 单一入口 load()):
 *  - GET /api/todos?limit=200            {version,total,items[]}
 *  - GET /api/kl/planning-actions?status=pending   顶层数组 (接口固定上限 50 条)
 *  - GET /api/reviews/due?limit=20       {version,count,items[]}
 *  - GET /api/reviews/stats              {version,stats:{total,due,avg_easiness}}
 *  - GET /api/secnews/stats              {new_today,...} → 心跳条「今日收录」
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SentinelShell } from './SentinelShell';
import './sentinel.css';
import './sentinel-action.css';

/* ---------------------------------------------------------------------
 * 接口响应类型 (与 backend/api/{todos,kl_planning_api,reviews}.py 对齐)
 * ------------------------------------------------------------------- */
interface TodoRow {
  id: number;
  source_type: string;
  source_id: string | null;
  title: string;
  url: string | null;
  source: string | null;
  category: string | null;
  /** Phase 46: 服务端由 deadline 派生后返回 */
  urgent: number;
  important: number;
  deadline: string | null;
  note: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
}

type ActionStatus = 'pending' | 'in_progress' | 'completed' | 'dismissed';

interface PlanningAction {
  id: number;
  item_id: string;
  action_type: string;
  priority: number;
  title: string;
  description: string | null;
  current_stage: string | null;
  target_stage: string | null;
  status: ActionStatus | string;
  created_at: string | null;
  completed_at: string | null;
  dismissed_at: string | null;
}

interface ReviewRow {
  id: string;
  entity_type: string;
  entity_id: string;
  easiness: number;
  interval: number;
  repetitions: number;
  due_at: string;
  last_grade: number | null;
  last_reviewed_at: string | null;
}

interface ReviewStats {
  total: number;
  due: number;
  avg_easiness: number;
}

/** 每行写入态: saving / fail / ok; 判读待办另带 done|dismissed */
type WriteState = 'saving' | 'fail' | 'ok' | 'done' | 'dismissed';

/** 快速捕获表单自身的写入态键 (todo.id 从 1 起, 负键不会与真实行冲突) */
const CAPTURE_KEY = -1;

const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];
/** planning_actions 接口单次固定返回 50 条, 本屏按优先级取前 N 条呈现 */
const ACTION_SHOWN = 8;
/** 复习栈视觉层数 (顶层可操作, 其后为队列中的真实后续卡) */
const STACK_DEPTH = 3;

/* ---------------------------------------------------------------------
 * 纯函数 helpers
 * ------------------------------------------------------------------- */

/** API 来源的 href 白名单: 只放行 http/https, 其余 (javascript:/data:) 一律不渲染链接 */
function safeHref(url?: string | null): string | null {
  if (!url) return null;
  return /^https?:\/\//i.test(url.trim()) ? url.trim() : null;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** 'YYYY-MM-DD' 本地日键; 非法 → null */
function dayKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function isoDayKey(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : dayKey(d);
}

function stamp(iso?: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
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

/** 本周一 00:00 (本地), 用于七日强度点阵定窗 */
function mondayOf(now: Date): Date {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const wd = d.getDay(); // 0=周日
  d.setDate(d.getDate() - (wd === 0 ? 6 : wd - 1));
  return d;
}

/** deadline 'YYYY-MM-DD' → 逾期/今日徽标文案 (逾期按纪律用 amber, 不占用 red) */
function deadlineText(deadline?: string | null): { text: string; warn: boolean } | null {
  const key = isoDayKey(deadline);
  if (!key) return null;
  const today = dayKey(new Date());
  const d = new Date(`${key}T00:00:00`);
  const t = new Date(`${today}T00:00:00`);
  const diff = Math.round((d.getTime() - t.getTime()) / 86400000);
  if (diff < 0) return { text: `逾期 ${Math.abs(diff)} 天`, warn: true };
  if (diff === 0) return { text: '今日到期', warn: true };
  if (diff <= 3) return { text: `${diff} 天后到期`, warn: true };
  return { text: `截止 ${key.slice(5).replace('-', '/')}`, warn: false };
}

/** 待办按 未完成 → 已完成 分组 (组内保持服务端 urgent/important/created 排序) */
function partitionTodos(rows: TodoRow[]): { open: TodoRow[]; done: TodoRow[] } {
  const open: TodoRow[] = [];
  const done: TodoRow[] = [];
  for (const t of rows) (t.status === 'done' || t.status === 'archived' ? done : open).push(t);
  return { open, done };
}

/** SM-2 自评三档 → grade (0-2 未记住, 3-5 记住) */
const GRADE_DEFS: { label: string; grade: number; hint: string }[] = [
  { label: '忘光', grade: 1, hint: '回到判断层重读原文' },
  { label: '模糊', grade: 3, hint: '间隔缩短, 近日再见' },
  { label: '记得牢', grade: 5, hint: '间隔拉长, 明日再见' },
];

const ACTION_TYPE_LABEL: Record<string, string> = {
  read: '深读',
  refine: '精读入库',
  link: '建立关联',
  publish: '产出输出',
  review: '复看',
};

/* ---------------------------------------------------------------------
 * 组件
 * ------------------------------------------------------------------- */
export function SentinelActionPage() {
  const navigate = useNavigate();

  const [todos, setTodos] = useState<TodoRow[]>([]);
  const [todoTotal, setTodoTotal] = useState(0);
  const [actions, setActions] = useState<PlanningAction[]>([]);
  const [reviews, setReviews] = useState<ReviewRow[]>([]);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [newToday, setNewToday] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [graded, setGraded] = useState(0);

  /** 行级写入态: key 为 todo id / planning action id / review id */
  const [todoState, setTodoState] = useState<Record<number, WriteState>>({});
  const [actionState, setActionState] = useState<Record<number, WriteState>>({});
  const [reviewState, setReviewState] = useState<Record<string, WriteState>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    const [td, pa, rv, rs, st] = await Promise.all([
      fetch('/api/todos?limit=200', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/kl/planning-actions?status=pending', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/reviews/due?limit=20', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/reviews/stats', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/secnews/stats', { headers: { Accept: 'application/json' } })
        .then(r => (r.ok ? r.json() : null)).catch(() => null),
    ]);

    if (td) {
      setTodos(Array.isArray(td.items) ? td.items : []);
      setTodoTotal(Number(td.total) || 0);
    }
    setActions(Array.isArray(pa) ? pa : []);
    setReviews(rv && Array.isArray(rv.items) ? rv.items : []);
    setReviewStats(rs?.stats ?? null);
    setNewToday(st && typeof st.new_today === 'number' ? st.new_today : null);
    setGraded(0);

    const failed = [td, pa, rv, st].filter(v => v == null).length;
    if (failed > 0) setNotice(`${failed} 个数据源本次未返回，显示的是可用数据`);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // 采集/入库事件到达时不整体重拉: 行动队列由人驱动, 重拉会吞掉行内乐观写入态;
  // 管道心跳条由 SentinelShell 自身维护。

  /* ---------------- 派生视图 ---------------- */
  const { open, done } = useMemo(() => partitionTodos(todos), [todos]);

  /** 七日强度点阵: 口径 = todos.completed_at 的每日完成数 (真实字段, 无估算) */
  const rhythm = useMemo(() => {
    const now = new Date();
    const monday = mondayOf(now);
    // 用「本地零点」相减求日序: now 含时分秒会让 round 在下午/周一两种场景漂一天
    const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const todayIdx = Math.min(6, Math.max(0, Math.round((todayMidnight.getTime() - monday.getTime()) / 86400000)));
    const counts = new Array(7).fill(0) as number[];
    let recorded = 0;
    for (const t of todos) {
      const key = isoDayKey(t.completed_at);
      if (!key || t.status !== 'done') continue;
      const idx = Math.round((new Date(`${key}T00:00:00`).getTime() - monday.getTime()) / 86400000);
      if (idx >= 0 && idx < 7) { counts[idx] += 1; recorded += 1; }
    }
    const hit = counts.filter(c => c > 0).length;
    const note = recorded > 0
      ? `今日完成 ${counts[todayIdx] ?? 0} 项 · 本周累计 ${recorded} 项`
      : '本周尚无完成记录 · 口径为待办完成时间';
    return {
      note,
      days: DAY_LABELS.map((label, i) => ({
        label,
        count: counts[i],
        on: counts[i] > 0,
        future: i > todayIdx,
        today: i === todayIdx,
      })),
      hit,
      todayDone: counts[todayIdx] ?? 0,
      recorded,
    };
  }, [todos]);

  const shownActions = useMemo(() => actions.slice(0, ACTION_SHOWN), [actions]);
  const stack = useMemo(() => reviews.slice(0, STACK_DEPTH), [reviews]);
  const top = stack[0] ?? null;

  /* ---------------- 写操作 ---------------- */

  /** 勾选/取消待办 → PATCH /api/todos/{id} {status} */
  const toggleTodo = useCallback(async (todo: TodoRow) => {
    if (todoState[todo.id] === 'saving') return;
    // archived 与 done 同属「已结束」: 取消勾选一律回到 open
    const finished = todo.status === 'done' || todo.status === 'archived';
    const next = finished ? 'open' : 'done';
    const prev = todo.status;
    const iso = new Date().toISOString();

    setTodoState(s => ({ ...s, [todo.id]: 'saving' }));
    setTodos(list => list.map(t => (t.id === todo.id
      ? { ...t, status: next, completed_at: next === 'done' ? iso : null }
      : t)));

    try {
      const r = await fetch(`/api/todos/${todo.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ status: next }),
      });
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      if (data?.item) setTodos(list => list.map(t => (t.id === todo.id ? { ...t, ...data.item } : t)));
      setTodoState(s => ({ ...s, [todo.id]: 'ok' }));
    } catch {
      setTodos(list => list.map(t => (t.id === todo.id ? { ...t, status: prev } : t)));
      setTodoState(s => ({ ...s, [todo.id]: 'fail' }));
    }
  }, [todoState]);

  /** 快速捕获 → POST /api/todos {source_type:'manual', title, important} */
  const addTodo = useCallback(async () => {
    const title = draft.trim();
    if (!title) return;
    setTodoState(s => ({ ...s, [CAPTURE_KEY]: 'saving' }));
    try {
      const r = await fetch('/api/todos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ source_type: 'manual', title, important: 0 }),
      });
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      if (data?.item) {
        setTodos(list => [data.item, ...list]);
        setTodoTotal(n => n + 1);
      }
      setDraft('');
      setTodoState(s => ({ ...s, [CAPTURE_KEY]: 'ok' }));
    } catch {
      setTodoState(s => ({ ...s, [CAPTURE_KEY]: 'fail' }));
    }
  }, [draft]);

  /**
   * 推进判读待办 → PUT /api/kl/planning-actions/{id}/status {status}
   * 服务端状态机只允许 pending→in_progress→completed|dismissed,
   * 因此一步「完成」需要链式两次 PUT; 中途失败则停在已确认的步骤并标 amber。
   */
  const advanceAction = useCallback(async (action: PlanningAction, target: ActionStatus) => {
    if (actionState[action.id] === 'saving') return;
    const steps: ActionStatus[] = action.status === 'pending' && target !== 'in_progress'
      ? ['in_progress', target]
      : [target];
    setActionState(s => ({ ...s, [action.id]: 'saving' }));
    let settled = action.status as ActionStatus;
    const iso = new Date().toISOString();

    for (const step of steps) {
      try {
        const r = await fetch(`/api/kl/planning-actions/${action.id}/status`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ status: step }),
        });
        if (!r.ok) throw new Error(String(r.status));
      } catch {
        setActions(list => list.map(a => (a.id === action.id ? { ...a, status: settled } : a)));
        setActionState(s => ({ ...s, [action.id]: 'fail' }));
        return;
      }
      settled = step;
      setActions(list => list.map(a => (a.id === action.id ? {
        ...a,
        status: step,
        completed_at: step === 'completed' ? iso : a.completed_at,
        dismissed_at: step === 'dismissed' ? iso : a.dismissed_at,
      } : a)));
    }
    setActionState(s => ({ ...s, [action.id]: target === 'completed' ? 'done' : 'dismissed' }));
  }, [actionState]);

  /** 复习评分 → POST /api/reviews/{entity_type}/{entity_id}/grade {grade:0-5} */
  const gradeReview = useCallback(async (row: ReviewRow, grade: number) => {
    if (reviewState[row.id] === 'saving') return;
    setReviewState(s => ({ ...s, [row.id]: 'saving' }));
    try {
      const r = await fetch(
        `/api/reviews/${encodeURIComponent(row.entity_type)}/${encodeURIComponent(row.entity_id)}/grade`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ grade }),
        },
      );
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      const next: ReviewRow | undefined = data?.item;
      const stillDue = !!next && new Date(next.due_at).getTime() <= Date.now();
      if (next && stillDue) {
        setReviews(list => list.map(x => (x.id === next.id ? next : x)));
      } else {
        setReviews(list => list.filter(x => x.id !== row.id));
        setReviewStats(s => (s ? { ...s, due: Math.max(0, s.due - 1) } : s));
      }
      setGraded(n => n + 1);
      setReviewState(s => ({ ...s, [row.id]: 'ok' }));
    } catch {
      setReviewState(s => ({ ...s, [row.id]: 'fail' }));
    }
  }, [reviewState]);

  /* ---------------- 渲染 ---------------- */
  const addState = todoState[CAPTURE_KEY];

  return (
    <SentinelShell layer="action" ingested={newToday}>
      <section className="ac-scr" aria-label="行动层 · 今日行动：复习栈、待办清单与判读待办">
        <header className="ac-head">
          <div>
            <span className="ac-kicker">ACTION FLOOR</span>
            <h1 className="ac-h1">今日<b>行动</b><span> / 04</span></h1>
            <p className="ac-sub">读完之后，动手的部分：复习、待办、判读队列都在这里推进。</p>
          </div>
          <div
            className="ac-rhythm"
            role="img"
            aria-label={`本周节奏：周一至周日中 ${rhythm.hit} 天有待办完成记录，今日完成 ${rhythm.todayDone} 项`}
          >
            <div className="ac-rh-head">
              <span className="ac-rh-t">本周节奏</span>
              <span className="ac-rh-c num">{rhythm.hit} / 7 达标</span>
            </div>
            <div className="ac-rh-cells">
              <span className="heat-cells" aria-hidden="true">
                {rhythm.days.map(d => (
                  <b
                    key={d.label}
                    className={`${d.on ? 'on' : ''} ${d.today ? 'ac-live' : ''}`.trim()}
                    title={d.count > 0 ? `${d.label}：完成 ${d.count} 项` : `${d.label}：无完成记录`}
                  />
                ))}
              </span>
              <span className="ac-days" aria-hidden="true">
                {rhythm.days.map(d => <i key={d.label}>{d.label}</i>)}
              </span>
            </div>
            <p className="ac-rh-note">{rhythm.note}</p>
          </div>
        </header>

        {notice && (
          <p className="ac-banner" role="status">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M6.5 1.8l5 9H1.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /><path d="M6.5 5.2v2.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="6.5" cy="9.2" r=".7" fill="currentColor" /></svg>
            {notice}
          </p>
        )}

        <div className="ac-grid">
          {/* ===== 复习栈 · SM-2 ===== */}
          <section className="ac-panel ac-review" aria-labelledby="ac-h-review">
            <header className="ac-ph">
              <h2 id="ac-h-review">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M2 4.5L6.5 2 11 4.5 6.5 7z" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /><path d="M2 7.5L6.5 10 11 7.5" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /></svg>
                复习栈
              </h2>
              <span className="ac-phn num">{reviewStats ? `${reviewStats.due} DUE` : '…'}</span>
            </header>

            {loading ? (
              <div className="ac-load" aria-busy="true"><div className="skel-line w1" /><div className="skel-line w2" /><div className="skel-line w3" /></div>
            ) : !top ? (
              <div className="ac-empty">
                <div className="ac-empty-ring" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="6.5" stroke="currentColor" strokeWidth="1.5" /><path d="M9 5.6V9l2.3 1.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                </div>
                <h3>今日复习栈已清空</h3>
                <p>到期队列为空。SM-2 会在下一次到期时把卡片排回来。</p>
              </div>
            ) : (
              <>
                <div className="ac-stack" aria-label={`复习栈 ${stack.length} 张到期卡片，最上层为当前待评分卡片`}>
                  {/* 绝对定位层序: 后续卡先入 DOM, 顶层卡最后渲染才压在上方 */}
                  {stack.slice(1).map((row, i) => {
                    const depth = stack.length - 1 - i; // 队列里往后第几张
                    return (
                      <article key={row.id} className={`ac-card ${depth >= 2 ? 'c2' : 'c1'}`} aria-hidden="true">
                        <div className="ac-cmeta">
                          <span className="ac-cdeck">{row.entity_type.toUpperCase()}</span>
                          <span>往后第 {depth} 张</span>
                        </div>
                        <p className="ac-ct" title={row.entity_id}>{row.entity_id}</p>
                      </article>
                    );
                  })}
                  {top && (() => {
                    const state = reviewState[top.id];
                    return (
                      <article className="ac-card top">
                        <div className="ac-cmeta">
                          <span className="ac-cdeck">{top.entity_type.toUpperCase()}</span>
                          <span>本次已评 {graded} 张</span>
                        </div>
                        <p className="ac-ct" title={top.entity_id}>{top.entity_id}</p>
                        <p className="ac-chint">
                          接口只提供实体标识（无标题字段）。{relTime(top.last_reviewed_at)}评过一次。
                        </p>
                        <div className="ac-sm2">
                          <span>EF <b className="num">{Number(top.easiness).toFixed(2)}</b></span>
                          <span>间隔 <b className="num">{top.interval}d</b></span>
                          <span>重复 <b className="num">{top.repetitions}</b></span>
                          <span>到期 <b className="num">{stamp(top.due_at)}</b></span>
                        </div>
                        <div className="ac-grade">
                          {GRADE_DEFS.map(g => (
                            <button
                              key={g.label}
                              type="button"
                              className="ac-gbtn"
                              title={`${g.label} → grade ${g.grade}：${g.hint}`}
                              disabled={state === 'saving'}
                              onClick={() => gradeReview(top, g.grade)}
                            >
                              {state === 'saving' ? '提交中' : g.label}
                              <span className="g num">g{g.grade}</span>
                            </button>
                          ))}
                        </div>
                        {state === 'fail' && <p className="ac-note is-fail" role="status">评分未写入成功，卡片仍在今日队列中。</p>}
                      </article>
                    );
                  })()}
                </div>
                <div className="ac-sched">
                  <span className="num ac-now">今日 {reviewStats?.due ?? stack.length}</span>
                  <i aria-hidden="true" />
                  <span className="num">在册 {reviewStats?.total ?? '--'}</span>
                  <i aria-hidden="true" />
                  <span className="num">平均 EF {reviewStats ? Number(reviewStats.avg_easiness).toFixed(2) : '--'}</span>
                </div>
                <p className="ac-self">自评机制：记得牢，间隔拉长；模糊，近日再见；忘光，回判断层重读原文。</p>
                <a className="ac-link" href="/judge" onClick={e => { e.preventDefault(); navigate('/judge'); }}>
                  去判断层重读原文
                  <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </a>
              </>
            )}
          </section>

          {/* ===== 待办清单 · /api/todos ===== */}
          <section className="ac-panel ac-todo" aria-labelledby="ac-h-todo">
            <header className="ac-ph">
              <h2 id="ac-h-todo">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><rect x="2" y="2" width="9" height="9" rx="2" stroke="currentColor" strokeWidth="1.5" /><path d="M4.5 6.6l1.7 1.7 3-3.4" stroke="currentColor" strokeWidth="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
                待办清单
              </h2>
              <span className="ac-phn num">{open.length} OPEN · {done.length} DONE</span>
            </header>

            {loading ? (
              <div className="ac-load" aria-busy="true"><div className="skel-line w2" /><div className="skel-line w1" /><div className="skel-line w3" /></div>
            ) : todos.length === 0 ? (
              <div className="ac-empty">
                <div className="ac-empty-ring" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="3" y="3" width="12" height="12" rx="2.5" stroke="currentColor" strokeWidth="1.5" /></svg>
                </div>
                <h3>还没有待办</h3>
                <p>在下方快速捕获丢一条进来，或从判断层把条目归档为待办。</p>
              </div>
            ) : (
              <ul className="ac-tlist">
                {[...open, ...done].map(t => {
                  const href = safeHref(t.url);
                  const dl = t.status === 'open' ? deadlineText(t.deadline) : null;
                  const state = todoState[t.id];
                  const isDone = t.status === 'done' || t.status === 'archived';
                  return (
                    <li key={t.id} className={isDone ? 'is-done' : undefined}>
                      <label>
                        <input
                          type="checkbox"
                          checked={isDone}
                          disabled={state === 'saving'}
                          onChange={() => toggleTodo(t)}
                          aria-label={`${isDone ? '取消完成' : '标记完成'}：${t.title}`}
                        />
                        <span className="ac-tbody">
                          <span className="ac-tt">
                            {href ? <a href={href} target="_blank" rel="noopener noreferrer">{t.title}</a> : t.title}
                          </span>
                          <span className="ac-tmeta">
                            <span>#{String(t.id).padStart(2, '0')}</span>
                            <span>{t.source_type === 'favorite' ? 'COLLECT' : 'MANUAL'}</span>
                            {t.important === 1 && <span>重要</span>}
                            {t.urgent === 1 && !isDone && <span className="due-warn">紧急</span>}
                            {dl && <span className={dl.warn ? 'due-miss' : undefined}>{dl.text}</span>}
                            <span>{stamp(t.completed_at ?? t.updated_at ?? t.created_at)}</span>
                            {state === 'saving' && <span className="ac-tstate saving">写入中</span>}
                            {state === 'fail' && <span className="ac-tstate fail" role="status">保存失败</span>}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}

            <div className="ac-qcap">
              <label className="sr-only" htmlFor="ac-qc">快速捕获新待办</label>
              <input
                id="ac-qc"
                type="text"
                value={draft}
                placeholder="想到什么，先丢进来"
                autoComplete="off"
                maxLength={500}
                disabled={addState === 'saving'}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTodo(); } }}
              />
              <button className="ac-add" type="button" disabled={!draft.trim() || addState === 'saving'} onClick={() => addTodo()}>
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M6.5 2.5v8M2.5 6.5h8" stroke="currentColor" strokeWidth="1.5" stroke-linecap="round" /></svg>
                {addState === 'saving' ? '添加中' : '添加'}
              </button>
            </div>
            <p className={`ac-qnote${addState === 'fail' ? ' is-fail' : ''}`} role="status">
              {addState === 'fail'
                ? '新增未写入成功，请重试。'
                : `共 ${todoTotal || todos.length} 条 · 新捕获按 manual 置顶，紧急由截止日期自动派生`}
            </p>
          </section>

          {/* ===== 判读待办 · planning_actions ===== */}
          <section className="ac-panel ac-out" aria-labelledby="ac-h-out">
            <header className="ac-ph">
              <h2 id="ac-h-out">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M3.5 12.5l.9-3.2 6.6-6.6 2.3 2.3-6.6 6.6z" stroke="currentColor" strokeWidth="1.5" stroke-linejoin="round" /><path d="M9.3 4.2l2.3 2.3" stroke="currentColor" strokeWidth="1.5" stroke-linecap="round" /></svg>
                判读待办
              </h2>
              <span className="ac-phn num">{actions.length} PENDING</span>
            </header>

            {loading ? (
              <div className="ac-load" aria-busy="true"><div className="skel-line w3" /><div className="skel-line w2" /><div className="skel-line w1" /></div>
            ) : shownActions.length === 0 ? (
              <div className="ac-empty">
                <div className="ac-empty-ring" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 9.5l3.5 3.5L15 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </div>
                <h3>判读队列已清空</h3>
                <p>没有待推进的规划动作。采集入库后会自动生成新的动作。</p>
              </div>
            ) : (
              <ul className="ac-dlist">
                {shownActions.map(a => {
                  const state = actionState[a.id];
                  const settled = state === 'done' || state === 'dismissed';
                  const badge = a.priority >= 8 ? 'hot' : a.priority >= 5 ? 'warm' : '';
                  return (
                    <li key={a.id}>
                      <div className="ac-drow">
                        <input
                          type="checkbox"
                          checked={a.status === 'completed'}
                          disabled={state === 'saving' || a.status === 'completed'}
                          onChange={() => advanceAction(a, 'completed')}
                          aria-label={`完成：${a.title}`}
                        />
                        <div className="ac-dbody">
                          <p className="ac-dt">
                            <span className={`ac-badge${badge ? ` ${badge}` : ''}`}>{ACTION_TYPE_LABEL[a.action_type] ?? a.action_type}</span>
                            <span className="ac-dtitle">{a.title}</span>
                          </p>
                          <p className="ac-dm">
                            <span>#{String(a.id).padStart(4, '0')}</span>
                            <span>P{a.priority}</span>
                            {a.current_stage && a.target_stage && (
                              <span className="stage">{a.current_stage} → {a.target_stage}</span>
                            )}
                            <span>{relTime(a.created_at)}</span>
                          </p>
                        </div>
                        <div className="ac-dops">
                          {state === 'saving' && <span className="ac-dstate doing" role="status">推进中</span>}
                          {state === 'fail' && (
                            <span className="ac-dstate fail" role="status">
                              {a.status === 'in_progress' ? '已推进一步' : '未写入'}
                            </span>
                          )}
                          {state === 'done' && <span className="ac-dstate done" role="status">已完成</span>}
                          {state === 'dismissed' && <span className="ac-dstate" role="status">已暂缓</span>}
                          {!settled && a.status !== 'dismissed' && (
                            <button
                              type="button"
                              className="ac-dbtn"
                              disabled={state === 'saving'}
                              onClick={() => advanceAction(a, 'dismissed')}
                            >
                              暂缓
                            </button>
                          )}
                          {a.status === 'in_progress' && !settled && (
                            <span className="ac-dstate doing">进行中</span>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <p className="ac-note">
              队列共 {actions.length} 条待推进（服务端单次上限 50 条，此处按优先级取前 {Math.min(ACTION_SHOWN, Math.max(actions.length, 1))} 条）。
              「完成」按状态机两步走：pending → 进行中 → 已完成；中途失败会停在已确认的那一步。
            </p>
            <a className="ac-link" href="/knowledge/compound" onClick={e => { e.preventDefault(); navigate('/knowledge/compound'); }}>
              查看复利台全量队列
              <svg width="11" height="11" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2.5 7h8M7.5 3.5L11 7l-3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </a>
          </section>
        </div>

        <p className="endnote">
          <span>行动层 · ACTION / 04</span>
          <span>待办 {open.length} 未结</span>
          <span>复习 {reviewStats?.due ?? '--'} 到期</span>
          <span>判读待办 {actions.length} 待推进</span>
          <span>本周达标 {rhythm.hit} / 7 天</span>
        </p>
      </section>
    </SentinelShell>
  );
}
