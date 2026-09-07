/**
 * v1.0 C10 — CaseDetail mutation 接线 反例测试 (R14/R15 业务闭环)
 *
 * 旧实现 (commit 137e460 之前): CaseDetail 全部只读, 无任何 mutation 按钮
 *   - actions map 渲染 status Badge 但不挂任何 onClick
 *   - artifacts map 同样只挂 Badge, 无 verify/accept/reject 按钮
 *   - 无 case close 按钮
 *   - 失败无 Toast 提示
 *
 * C10 修复后:
 *   - 每个 action 块根据 status 显 1+ mutation 按钮 (approve/start/cancel)
 *   - 每个 artifact 块根据 status 显 1+ mutation 按钮 (verify/accept/reject)
 *   - CaseDetail 顶部加 close 按钮 (走 allowed_actions 守卫)
 *   - 所有 mutation 走 mutationHandlers 包装, 成功 Toast.success + refetch
 *   - 失败 Toast.error (含 status_code + 错误体), 输入保留, 不静默失败
 *   - 409 (E_CONFLICT) 显式标 E_CONFLICT 状态不冒充成功
 *
 * 反例 (旧实现必失败):
 *   R14.1 无任何 mutation 按钮渲染 (CaseDetail 不允许纯只读, 任务书 §11)
 *   R14.2 close 按钮不存在 (R17 close 守卫 4 件 UI 入口)
 *   R14.3 mutation 失败不显 Toast (silent failure, 违反 Mimosa "失败必 raise")
 *   R14.4 mutation 成功不刷新列表 (成功后 status 不变, 旧数据冒充新状态)
 *   R15.1 按钮不按 allowed_actions 守卫 (不论状态都显 → 用户点无效按钮 = 失败冒充)
 *   R15.2 状态非终态的 action 仍显 cancel 按钮 (应为 409 拒绝, 不是 UI 隐藏)
 *   R15.3 未 verify 的 artifact 显 accept 按钮 (R08: accept 必先 verify)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ToastProvider } from '../../Toast';
import { CaseDetail } from '../V1Prototype';
import type { Case, Judgment } from '../../../domain/v1_0';
import type { Action, Artifact, Run, Knowledge } from '../../../api/v1';

// Mock api v1
vi.mock('../../../api/v1', async () => {
  const actual = await vi.importActual<typeof import('../../../api/v1')>('../../../api/v1');
  return {
    ...actual,
    approveAction: vi.fn(),
    startAction: vi.fn(),
    cancelAction: vi.fn(),
    verifyArtifact: vi.fn(),
    acceptArtifact: vi.fn(),
    rejectArtifact: vi.fn(),
    closeCase: vi.fn(),
    getCase: vi.fn(),
    listJudgments: vi.fn(),
    listActions: vi.fn(),
    listRuns: vi.fn(),
    listArtifacts: vi.fn(),
    listKnowledge: vi.fn(),
    getKnowledgeReuse: vi.fn(),
  };
});
import * as api from '../../../api/v1';

function makeCase(over: Partial<Case> = {}): Case {
  return {
    id: 'C' + '0'.repeat(25),
    title: 'test case',
    question: 'q',
    status: 'in_progress' as any,
    priority: 'normal' as any,
    tags_json: '[]',
    revision: 1,
    created_at: '2026-09-07T00:00:00+00:00',
    updated_at: '2026-09-07T00:00:00+00:00',
    allowed_actions: ['start', 'close'] as any,
    reason: null,
    closed_at: null,
    subject_ids: [],
    signal_count: 0,
    judgment_count: 0,
    action_count: 1,
    artifact_count: 0,
    ...over,
  } as Case;
}

function makeAction(over: Partial<Action> = {}): Action {
  return {
    id: 'A' + '0'.repeat(25),
    case_id: 'C' + '0'.repeat(25),
    title: 'collect',
    plan: 'p',
    plan_hash: 'h' + '0'.repeat(63),
    tool_versions_json: '{}',
    expected_artifacts_json: '[]',
    status: 'planned' as any,
    revision: 1,
    created_at: '2026-09-07T00:00:00+00:00',
    updated_at: '2026-09-07T00:00:00+00:00',
    allowed_actions: ['approve', 'cancel'] as any,
    ...over,
  } as Action;
}

function makeArtifact(over: Partial<Artifact> = {}): Artifact {
  return {
    id: 'F' + '0'.repeat(25),
    run_id: 'R' + '0'.repeat(25),
    action_id: 'A' + '0'.repeat(25),
    title: 'report.md',
    format: 'markdown',
    size_bytes: 1024,
    content_hash: 'h' + '0'.repeat(63),
    content_ref: '/tmp/art.md',
    status: 'pending' as any,
    revision: 1,
    created_at: '2026-09-07T00:00:00+00:00',
    updated_at: '2026-09-07T00:00:00+00:00',
    allowed_actions: ['verify'] as any,
    verified_at: null,
    verified_by: null,
    verified_result: null,
    accepted_at: null,
    accepted_by: null,
    rejected_at: null,
    rejected_by: null,
    rejection_reason: null,
    superseded_by: null,
    ...over,
  } as Artifact;
}

function setupMocks(over: {
  case_?: Partial<Case>;
  action?: Partial<Action>;
  artifact?: Partial<Artifact>;
  run?: Partial<Run>;
  approveAction?: ReturnType<typeof vi.fn>;
  startAction?: ReturnType<typeof vi.fn>;
  verifyArtifact?: ReturnType<typeof vi.fn>;
  acceptArtifact?: ReturnType<typeof vi.fn>;
  rejectArtifact?: ReturnType<typeof vi.fn>;
  cancelAction?: ReturnType<typeof vi.fn>;
  closeCase?: ReturnType<typeof vi.fn>;
} = {}) {
  const c = makeCase(over.case_);
  const a = makeAction(over.action);
  const art = makeArtifact(over.artifact);
  const r: Run = {
    id: 'R' + '0'.repeat(25),
    action_id: a.id,
    attempt: 1,
    status: 'succeeded' as any,
    protocol: 'dsh',
    ticket_id: 't' + '0'.repeat(25),
    skill_id: 'SK-01',
    started_at: '2026-09-07T00:00:00+00:00',
    finished_at: '2026-09-07T00:00:01+00:00',
    error: null,
    output_ref: null,
    revision: 1,
    ...over.run,
  } as Run;
  (api.getCase as any).mockResolvedValue({ item: c });
  (api.listJudgments as any).mockResolvedValue({ items: [] as Judgment[] });
  (api.listActions as any).mockResolvedValue({ items: [a] });
  (api.listRuns as any).mockResolvedValue({ items: [r] });
  (api.listArtifacts as any).mockResolvedValue({ items: [art] });
  (api.listKnowledge as any).mockResolvedValue({ items: [] as Knowledge[] });
  (api.getKnowledgeReuse as any).mockResolvedValue({ receipt: { total: 0, by_judgment: 0, by_action: 0, recent_30d: 0 } });
  if (over.approveAction) (api.approveAction as any).mockImplementation(over.approveAction);
  if (over.startAction) (api.startAction as any).mockImplementation(over.startAction);
  if (over.cancelAction) (api.cancelAction as any).mockImplementation(over.cancelAction);
  if (over.verifyArtifact) (api.verifyArtifact as any).mockImplementation(over.verifyArtifact);
  if (over.acceptArtifact) (api.acceptArtifact as any).mockImplementation(over.acceptArtifact);
  if (over.rejectArtifact) (api.rejectArtifact as any).mockImplementation(over.rejectArtifact);
  if (over.closeCase) (api.closeCase as any).mockImplementation(over.closeCase);
  return { case_: c, action: a, artifact: art, run: r };
}

function renderWithToast(ui: React.ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe('v1.0 C10 R14/R15 mutation 接线', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ---------------- R14 业务闭环 ----------------

  it('R14.1 CaseDetail 渲染 action 块时必带 approve/start/cancel 至少 1 个 mutation 按钮', async () => {
    setupMocks();
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalled());
    // 旧实现 0 按钮 → 此断言失败
    const buttons = await screen.findAllByRole('button');
    const labels = buttons.map(b => b.textContent ?? '');
    expect(labels.some(l => /approve|start|cancel|批准|启动|取消/.test(l))).toBe(true);
  });

  it('R14.2 CaseDetail 顶部必带 close 按钮 (case close 4 守卫 UI 入口)', async () => {
    setupMocks({ case_: { allowed_actions: ['close'] as any } });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.getCase).toHaveBeenCalled());
    // 旧实现无 close 按钮
    expect(await screen.findByRole('button', { name: /关闭事项|close|关闭/ })).toBeTruthy();
  });

  it('R14.3 mutation 失败 (5xx) 必弹 Toast error, 不静默 (Mimosa 禁 silent)', async () => {
    setupMocks({
      approveAction: vi.fn().mockRejectedValue(new Error('E_CONFLICT: revision mismatch')),
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalled());
    const approveBtn = await screen.findByRole('button', { name: /approve|批准/ });
    fireEvent.click(approveBtn);
    await waitFor(() => {
      expect(screen.getByText(/E_CONFLICT|revision mismatch|失败/)).toBeTruthy();
    });
  });

  it('R14.4 mutation 成功后必刷新 actions (status 从 planned 变 approved)', async () => {
    const updated = makeAction({ status: 'approved' as any, revision: 2 });
    setupMocks({
      approveAction: vi.fn().mockResolvedValue({ item: updated }),
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalledTimes(1));
    const approveBtn = await screen.findByRole('button', { name: /approve|批准/ });
    fireEvent.click(approveBtn);
    await waitFor(() => {
      // 成功后必触发至少第 2 次 listActions (refetch)
      expect((api.listActions as any).mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  // ---------------- R15 状态机守卫 ----------------

  it('R15.1 close 按钮仅当 case.allowed_actions 含 close 时显示', async () => {
    setupMocks({ case_: { allowed_actions: [] as any } });
    renderWithToast(<CaseDetail case_={makeCase({ allowed_actions: [] as any })} onBack={() => {}} />);
    await waitFor(() => expect(api.getCase).toHaveBeenCalled());
    // 不在 allowed_actions → 不应显 close 按钮
    expect(screen.queryByRole('button', { name: /关闭事项|关闭/ })).toBeNull();
  });

  it('R15.2 action status=approved 必带 start 按钮 (走 allowed_actions 守卫)', async () => {
    setupMocks({
      action: { status: 'approved' as any, allowed_actions: ['start', 'cancel'] as any },
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: /start|启动/ })).toBeTruthy();
  });

  it('R15.3 artifact status=pending 必带 verify 按钮 (R08: accept 必先 verify)', async () => {
    setupMocks({
      artifact: { status: 'pending' as any, allowed_actions: ['verify'] as any },
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: /verify|验证/ })).toBeTruthy();
    // pending 状态不该有 accept 按钮 (R08 守卫)
    expect(screen.queryByRole('button', { name: /accept|验收/ })).toBeNull();
  });

  it('R15.4 artifact status=verified 必带 accept + reject 按钮', async () => {
    setupMocks({
      artifact: { status: 'verified' as any, allowed_actions: ['accept', 'reject'] as any },
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.listActions).toHaveBeenCalled());
    expect(await screen.findByRole('button', { name: /accept|验收/ })).toBeTruthy();
    expect(await screen.findByRole('button', { name: /reject|拒绝/ })).toBeTruthy();
  });

  // ---------------- 失败保留输入 + 409 显式 ----------------

  it('R14.5 closeCase 失败 409 必 Toast error 含 conflict 字样, 不冒充关闭', async () => {
    setupMocks({
      case_: { allowed_actions: ['close'] as any, status: 'in_progress' as any, revision: 3 },
      closeCase: vi.fn().mockRejectedValue(
        Object.assign(new Error('E_CONFLICT: active runs exist'), { code: 'E_CONFLICT', current_revision: 3 }),
      ),
    });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.getCase).toHaveBeenCalled());
    const closeBtn = await screen.findByRole('button', { name: /关闭事项|close|关闭/ });
    fireEvent.click(closeBtn);
    await waitFor(() => {
      expect(screen.getByText(/active runs|E_CONFLICT|失败/)).toBeTruthy();
    });
    // 不冒充成功: 必不调 getCase 标 closed
    expect((api.getCase as any).mock.calls.length).toBe(1);
  });
});
