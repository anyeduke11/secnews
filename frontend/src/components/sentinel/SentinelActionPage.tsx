/**
 * SentinelActionPage — 哨兵终端 · 行动层「今日行动」(V2 设计稿 ACTION FLOOR 屏)
 *
 * 信息架构: 三层工作流的行动层 — 计划、学习、输出。双栏布局契约 ac-grid:
 *  - 复习栈   ← SM-2 间隔重复 (可评分: POST /api/reviews/{type}/{id}/grade)
 *  - 判读待办 ← planning_actions (可推进: PUT /api/kl/planning-actions/{id}/status)
 *
 * R-13: 待办清单 (todos) 已随待办域退役移除, 本屏不再消费 /api/todos。
 *
 * 本屏要点: planning_actions 历史上 100% pending、无 UI 完成入口,
 * 这里是「推进行动队列」首次成为一等公民 → 全部写操作走乐观更新 + 失败回滚,
 * 不做只读展示。复习卡片仅有 entity_type/entity_id (接口无标题字段), 如实渲染。
 *
 * 数据源 (全部真实 API, 单一入口 load()):
 *  - GET /api/kl/planning-actions?status=pending   顶层数组 (接口固定上限 50 条)
 *  - GET /api/reviews/due?limit=20&enrich=1   {version,count,items[]}(migration 120 enrich)
 *  - GET /api/reviews/stats              {version,stats:{total,due,avg_easiness,...}}
 *  - GET /api/secnews/stats              {new_today,...} → 心跳条「今日收录」
 *
 * 复习栈能力丰富 (2026-09-21 设计稿 §4.1): 卡片标题化 / 评分即时反馈
 * ("下次 N 天后见") / 5 秒撤销窗 / 键盘 1·3·5 快捷评分 / 页内全屏
 * ReviewOverlay (会话·数据·管理三视图, 零新增路由)。
 *
 * B5 (2026-11-18) 绞杀者拆分: 原 576 行单文件按区块拆为 action/ 下 4 个文件
 * (actionModel / ActionFloorHeader / ReviewStackPanel / JudgingQueuePanel),
 * 本文件只保留状态、取数、写操作编排与区块组合; DOM / class / aria 与拆分前逐字一致。
 * R1 裁决 (2026-11-18): 补挂 v1 CaseQueuePanel (blocked 队列此前无 UI 入口)。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listPlanningActions,
  getReviewStats,
  listDueReviews,
  submitReviewGrade,
  undoReviewGrade,
  updatePlanningActionStatus,
} from '../../api/action';
import { getSecNewsStats } from '../../api/secnews';
import { SentinelShell } from '../../shell/AppShell';
import { ApprovalInbox } from '../action/ApprovalInbox';
import { CopilotCards } from '../action/CopilotCards';
import { CaseQueuePanel } from '../v1/panels/CaseQueuePanel';
import { ExecOverviewPanel } from '../v1/panels/ExecOverviewPanel';
import { ActionCommandConsole } from './action/ActionCommandConsole';
import { ActionFloorHeader } from './action/ActionFloorHeader';
import { ReviewStackPanel } from './action/ReviewStackPanel';
import { JudgingQueuePanel } from './action/JudgingQueuePanel';
import {
  ACTION_SHOWN, GRADE_DEFS, STACK_DEPTH, reviewTitle,
  type ActionStatus, type JustGraded, type PlanningAction,
  type ReviewRow, type ReviewStats, type WriteState,
} from './action/actionModel';
import { ReviewOverlay, type RvView } from './review/ReviewOverlay';
import './sentinel.css';
import './sentinel-action.css';

/* ---------------------------------------------------------------------
 * 组件
 * ------------------------------------------------------------------- */
export function SentinelActionPage() {
  const navigate = useNavigate();

  const [actions, setActions] = useState<PlanningAction[]>([]);
  const [reviews, setReviews] = useState<ReviewRow[]>([]);
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [newToday, setNewToday] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [graded, setGraded] = useState(0);
  /** ReviewOverlay 当前视图 (null = 关闭) */
  const [overlayView, setOverlayView] = useState<RvView | null>(null);
  /** 评分即时反馈 + 5 秒撤销窗 */
  const [justGraded, setJustGraded] = useState<JustGraded | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** 行级写入态: key 为 planning action id / review id */
  const [actionState, setActionState] = useState<Record<number, WriteState>>({});
  const [reviewState, setReviewState] = useState<Record<string, WriteState>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    const [pa, rv, rs, st] = await Promise.all([
      // apiFetch 非 ok / 网络失败抛错 → null (对应原 r.ok 分支检查 + .catch(() => null))
      listPlanningActions<PlanningAction>('pending').catch(() => null),
      listDueReviews<ReviewRow>(20, { enrich: true }).catch(() => null),
      getReviewStats<ReviewStats>().catch(() => null),
      getSecNewsStats<{ new_today?: number }>().catch(() => null),
    ]);

    setActions(Array.isArray(pa) ? pa : []);
    setReviews(rv && Array.isArray(rv.items) ? rv.items : []);
    setReviewStats(rs?.stats ?? null);
    setNewToday(st && typeof st.new_today === 'number' ? st.new_today : null);
    setGraded(0);

    const failed = [pa, rv, st].filter(v => v == null).length;
    if (failed > 0) setNotice(`${failed} 个数据源本次未返回，显示的是可用数据`);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  // 采集/入库事件到达时不整体重拉: 行动队列由人驱动, 重拉会吞掉行内乐观写入态;
  // 管道心跳条由 SentinelShell 自身维护。

  /* ---------------- 派生视图 ---------------- */
  const shownActions = useMemo(() => actions.slice(0, ACTION_SHOWN), [actions]);
  const stack = useMemo(() => reviews.slice(0, STACK_DEPTH), [reviews]);
  const top = stack[0] ?? null;

  /* ---------------- 写操作 ---------------- */

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
        // apiFetch 非 ok 抛错 → 就地 catch 回滚到已确认步骤 (原实现 throw 后由同一 catch 接住)
        await updatePlanningActionStatus(action.id, step);
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

  /** 复习评分 → POST /api/reviews/{entity_type}/{entity_id}/grade {grade:0-5}
   *  成功后开启 "下次 N 天后见" 反馈与 5 秒撤销窗 (migration 120)。 */
  const gradeReview = useCallback(async (row: ReviewRow, grade: number) => {
    if (reviewState[row.id] === 'saving') return;
    setReviewState(s => ({ ...s, [row.id]: 'saving' }));
    try {
      const data = await submitReviewGrade<{ item?: ReviewRow }>(
        row.entity_type,
        row.entity_id,
        grade,
      );
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
      // 即时反馈 + 5s 撤销窗 (新评分会重置窗口)
      if (undoTimer.current) clearTimeout(undoTimer.current);
      setJustGraded({
        key: row.id,
        entityType: row.entity_type,
        entityId: row.entity_id,
        title: reviewTitle(row),
        interval: typeof next?.interval === 'number' ? next.interval : null,
      });
      undoTimer.current = setTimeout(() => setJustGraded(null), 5000);
    } catch {
      setReviewState(s => ({ ...s, [row.id]: 'fail' }));
    }
  }, [reviewState]);

  /** 撤销刚才的评分 → POST undo; 成功后重拉队列; 409 (无活跃 log) 静默收窗。 */
  const undoJustGraded = useCallback(async () => {
    const jg = justGraded;
    if (!jg) return;
    if (undoTimer.current) clearTimeout(undoTimer.current);
    undoTimer.current = null;
    setJustGraded(null);
    try {
      await undoReviewGrade(jg.entityType, jg.entityId);
      await load();
    } catch {
      /* 409 等: 窗口已收起, 不打扰 */
    }
  }, [justGraded, load]);

  // 卸载清理撤销窗定时器
  useEffect(() => () => {
    if (undoTimer.current) clearTimeout(undoTimer.current);
  }, []);

  // 键盘 1/3/5 快捷评分 (面板聚焦场景; overlay 打开时由 overlay 接管按键)
  useEffect(() => {
    if (overlayView !== null) return;
    const onKey = (e: KeyboardEvent) => {
      if (!top) return;
      const el = e.target as HTMLElement | null;
      if (el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)) return;
      const hit = GRADE_DEFS.find(g => String(g.grade) === e.key);
      if (hit) gradeReview(top, hit.grade);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [overlayView, top, gradeReview]);

  /* ---------------- 渲染 ---------------- */

  return (
    <SentinelShell layer="action" ingested={newToday}>
      <section className="ac-scr" aria-label="行动层 · 今日行动：复习栈与判读待办">
        <ActionFloorHeader notice={notice} />

        {/* R-15 四段执行指挥台: Case → Claim → Run → Artifact, 行动菜单主体 */}
        <ActionCommandConsole />

        <div className="ac-grid">
          <ReviewStackPanel
            loading={loading}
            reviewStats={reviewStats}
            stack={stack}
            top={top}
            graded={graded}
            reviewState={reviewState}
            justGraded={justGraded}
            onGrade={(row, grade) => { void gradeReview(row, grade); }}
            onUndo={() => { void undoJustGraded(); }}
            onOpenOverlay={setOverlayView}
            onGoNews={() => navigate('/')}
          />

          <JudgingQueuePanel
            loading={loading}
            actions={actions}
            shownActions={shownActions}
            actionState={actionState}
            onAdvance={(action, target) => { void advanceAction(action, target); }}
            onGoCompound={() => navigate('/knowledge/compound')}
          />
        </div>

        <p className="endnote">
          <span>行动层 · ACTION / 04</span>
          <span>复习 {reviewStats?.due ?? '--'} 到期</span>
          <span>判读待办 {actions.length} 待推进</span>
        </p>

        {/* v0.8.6 M3 副驾四卡 (P1-3): 起草入口 → 下方审批收件箱人审 → 双签 Run + 产物 */}
        <CopilotCards />

        {/* v0.8.6 M1 能力区块: AI 提案审批收件箱 (用例 A; Case 页起草 → 此处人审 → 双签 Run) */}
        <ApprovalInbox />

        {/* R1 补挂 (2026-11-18): v1.0 能力区块 · Case 队列 (blocked 置顶, → /cases/:id 研判) */}
        <CaseQueuePanel />

        {/* v0.8.5 能力区块: 执行与验收总览 (SK-03/04, 待批准/运行中/待验收; → /cases/:id?section=actions) */}
        <ExecOverviewPanel />

        {/* 复习栈页内全屏弹层 (会话/数据/管理三视图, 零新增路由) */}
        <ReviewOverlay
          open={overlayView !== null}
          view={overlayView ?? 'session'}
          onViewChange={setOverlayView}
          onClose={() => setOverlayView(null)}
          onDataChanged={() => { void load(); }}
        />
      </section>
    </SentinelShell>
  );
}
