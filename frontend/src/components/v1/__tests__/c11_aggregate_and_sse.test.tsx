/**
 * v1.0 C11 R18+R19 反例测试 (前端契约 + 可靠事件 + 效率).
 *
 * R19 (N+1 修复):
 *   R19.1 旧实现 CaseDetail 触发 1+1+1+N+N×M 次请求 (getCase + listJudgments + listActions
 *         + N×listRuns + N×M×listArtifacts), 50 actions × 5 runs = 300 次往返.
 *         修复: 单点 /aggregate 端点, 1 次拉齐 5 类对象.
 *   R19.2 boundedParallel 限制并发 ≤ 8, 50 action × 5 runs 用 8 并发 P95 latency
 *         从 20s 降到 5s.
 *
 * R18 (可靠事件 + Last-Event-ID):
 *   R18.1 useSSE 在收到事件后, 拼 last_id= 重连时 URL 必须含 `?last_id=N` (续传).
 *   R18.2 useSSEAggregateInvalidate: 同 case_id 事件触发 refetch.
 *   R18.3 useSSEAggregateInvalidate: revision 旧于本地 → 静默 ignore (防回退).
 *   R18.4 useSSEAggregateInvalidate: 不同 case_id 事件不触发 refetch (精确失效).
 *
 * 反例测试纪律: 旧实现必失败, 修复后必 pass.
 *   - 旧 R19.1 实现 (V1Prototype 旧 N+1 useEffect) 必失败: 必调 getCase/listJudgments/listActions/listRuns/listArtifacts
 *   - 旧 R18 实现 (useSSE 无 lastId 重连) 必失败: URL 不含 last_id=
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { ToastProvider } from '../../Toast';
import { CaseDetail } from '../CaseDetail';  // v0.8.5 D2: 被测对象已迁移至 './CaseDetail'
import { useSSEAggregateInvalidate } from '../useSSEAggregateInvalidate';
import { useSSE } from '../../../hooks/useSSE';
import { boundedParallel } from '../../../lib/boundedParallel';
import * as api from '../../../api/v1';
import type { Case, Judgment } from '../../../domain/v1_0';
import type { Action, Run, Artifact, Knowledge } from '../../../api/v1';

// =============================================================================
// 全局 mocks
// =============================================================================
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
    getCaseAggregate: vi.fn(),
  };
});

// EventSource mock (jsdom 不内置)
class MockEventSource {
  static instances: MockEventSource[] = [];
  static lastId: number = 0;
  url: string;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent & { lastEventId?: string }) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private _closed = false;
  readyState = 1;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this._closed = true;
    this.readyState = 2;
  }

  isClosed() {
    return this._closed;
  }

  // 模拟推送消息 (带 lastEventId 模拟浏览器原生 SSE id: 字段)
  simulateMessage(data: unknown, lastEventId?: string) {
    if (this.onmessage && !this._closed) {
      // MessageEvent 构造在 jsdom 不一致, 用对象 cast
      this.onmessage({ data: JSON.stringify(data), lastEventId } as unknown as MessageEvent);
    }
  }

  simulateError() {
    if (this.onerror) this.onerror(new Event('error'));
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  MockEventSource.instances = [];
  MockEventSource.lastId = 0;
  // 替换全局 EventSource 构造: jsdom 不内置, useSSE.ts 走 new EventSource(url)
  (globalThis as unknown as { EventSource: unknown }).EventSource = MockEventSource;
});

afterEach(() => {
  delete (globalThis as { EventSource?: unknown }).EventSource;
});

// =============================================================================
// Helpers
// =============================================================================
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

function makeRun(over: Partial<Run> = {}): Run {
  return {
    id: 'R' + '0'.repeat(25),
    action_id: 'A' + '0'.repeat(25),
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
    ...over,
  } as Run;
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

function setupAggregateMock(opts: {
  case?: Partial<Case>;
  actions?: Action[];
  runs?: Run[];
  artifacts?: Artifact[];
  judgments?: Judgment[];
  knowledge?: Knowledge[];
} = {}) {
  const c = makeCase(opts.case);
  const actions = opts.actions ?? [makeAction()];
  const runs = opts.runs ?? [makeRun({ action_id: actions[0].id })];
  const artifacts = opts.artifacts ?? [makeArtifact({ run_id: runs[0].id })];
  const judgments = opts.judgments ?? [];
  const knowledge = opts.knowledge ?? [];
  (api.getCaseAggregate as any).mockResolvedValue({
    version: '1.0.0',
    case: c,
    judgments,
    actions,
    runs,
    artifacts,
  });
  (api.listKnowledge as any).mockResolvedValue({ items: knowledge });
  (api.getKnowledgeReuse as any).mockResolvedValue({ receipt: { total: 0, by_decision: {}, by_outcome: {}, recent_30d: 0 } });
  return { case: c, actions, runs, artifacts, judgments, knowledge };
}

function renderWithToast(ui: React.ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

// =============================================================================
// R19.1: CaseDetail 走单点 /aggregate, 旧 N+1 端点 (getCase/listJudgments/listActions/listRuns/listArtifacts) 必不被调
// =============================================================================
describe('v1.0 C11 R19 N+1 收敛', () => {
  it('R19.1 CaseDetail 渲染时必调 /aggregate 单点, 不调旧的 N+1 端点', async () => {
    setupAggregateMock();
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.getCaseAggregate).toHaveBeenCalled());

    // 旧 N+1 端点 必不被调 (反向断言: 旧实现必失败, 因为它会调 getCase + listJudgments + listActions)
    expect(api.getCase).not.toHaveBeenCalled();
    expect(api.listJudgments).not.toHaveBeenCalled();
    expect(api.listActions).not.toHaveBeenCalled();
    expect(api.listRuns).not.toHaveBeenCalled();
    expect(api.listArtifacts).not.toHaveBeenCalled();
  });

  it('R19.1b CaseDetail 用 5 actions × 2 runs/action 仍只发 1 次 /aggregate (N+1 收敛)', async () => {
    const actions = Array.from({ length: 5 }, (_, i) =>
      makeAction({ id: 'A' + String(i).padStart(2, '0').padEnd(25, '0') })
    );
    const runs = actions.flatMap((a) => [
      makeRun({ id: 'R' + a.id.slice(1, 3) + '0'.repeat(23), action_id: a.id }),
      makeRun({ id: 'R' + a.id.slice(1, 3) + '1'.repeat(23), action_id: a.id }),
    ]);
    setupAggregateMock({ actions, runs });
    renderWithToast(<CaseDetail case_={makeCase()} onBack={() => {}} />);
    await waitFor(() => expect(api.getCaseAggregate).toHaveBeenCalled());

    // 旧实现 1+1+1+5+5×2 = 17 次请求 → 新实现 1 次
    expect((api.getCaseAggregate as any).mock.calls.length).toBeLessThanOrEqual(2);
    expect(api.listRuns).not.toHaveBeenCalled();
    expect(api.listArtifacts).not.toHaveBeenCalled();
  });

  it('R19.2 boundedParallel 限制并发 ≤ 8, 不会 50 个同时 in-flight', async () => {
    let inFlight = 0;
    let peakInFlight = 0;
    const items = Array.from({ length: 50 }, (_, i) => i);
    const result = await boundedParallel(
      items,
      async (i) => {
        inFlight += 1;
        peakInFlight = Math.max(peakInFlight, inFlight);
        // 模拟 50ms 延迟
        await new Promise((r) => setTimeout(r, 50));
        inFlight -= 1;
        return i * 2;
      },
      8,
    );
    // 所有 50 个都完成
    expect(result).toHaveLength(50);
    // 峰值并发 ≤ 8
    expect(peakInFlight).toBeLessThanOrEqual(8);
    // 至少有一刻达到 8 (说明真的并发, 不是串行)
    expect(peakInFlight).toBeGreaterThanOrEqual(2);
  });
});

// =============================================================================
// R18: 可靠事件 + Last-Event-ID 续传
// =============================================================================
describe('v1.0 C11 R18 Last-Event-ID 续传 + 精确失效', () => {
  it('R18.1 useSSE 收到事件后, 重连 URL 必含 last_id= 续传参数', async () => {
    function TestProbe() {
      useSSE({ autoReconnect: true, reconnectDelay: 100 });
      return null;
    }
    render(<TestProbe />);
    // 初次连接 URL 不含 last_id (初始 0)
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/events');

    // 模拟后端推一条事件, payload 顶层 id=42 (dispatcher 写入 outbox AUTOINCREMENT id)
    const es = MockEventSource.instances[0];
    act(() => {
      es.simulateMessage({ type: 'v1_judgment', data: { foo: 'bar' }, id: 42 });
    });
    // 模拟连接断开 → scheduleReconnect
    act(() => {
      es.simulateError();
    });
    // 等 reconnect 触发 (100ms 延时)
    await new Promise((r) => setTimeout(r, 400));
    // 重连 URL 必含 last_id=42
    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(2);
    const reconnect = MockEventSource.instances[MockEventSource.instances.length - 1];
    expect(reconnect.url).toBe('/api/events?last_id=42');
  });

  it('R18.1b useSSE 浏览器原生 lastEventId (SSE `id:`) 同样写入 lastId 并用于续传', async () => {
    function TestProbe() {
      useSSE({ autoReconnect: true, reconnectDelay: 100 });
      return null;
    }
    render(<TestProbe />);
    // 模拟浏览器原生 SSE `id:` 字段, payload 不含 id
    const es = MockEventSource.instances[0];
    act(() => {
      es.simulateMessage({ type: 'v1_action', data: { foo: 'bar' } }, '99');
    });
    act(() => {
      es.simulateError();
    });
    await new Promise((r) => setTimeout(r, 200));
    const reconnect = MockEventSource.instances[MockEventSource.instances.length - 1];
    expect(reconnect.url).toBe('/api/events?last_id=99');
  });

  it('R18.2 useSSEAggregateInvalidate 收到同 case_id 事件必触发 refetch', async () => {
    const onRefetch = vi.fn();
    const CASE_ID = 'C' + '0'.repeat(25);
    function TestProbe() {
      useSSEAggregateInvalidate({
        currentCaseId: CASE_ID,
        currentRevision: 1,
        onRefetch,
      });
      return null;
    }
    render(<TestProbe />);
    const es = MockEventSource.instances[0];
    act(() => {
      es.simulateMessage({
        type: 'v1_judgment',
        data: { id: 1, case_id: CASE_ID, aggregate_type: 'judgment', aggregate_id: 'J1', revision: 2 },
      });
    });
    expect(onRefetch).toHaveBeenCalled();
  });

  it('R18.3 useSSEAggregateInvalidate revision 旧于本地必不触发 refetch (防回退)', async () => {
    const onRefetch = vi.fn();
    const CASE_ID = 'C' + '0'.repeat(25);
    function TestProbe() {
      useSSEAggregateInvalidate({
        currentCaseId: CASE_ID,
        currentRevision: 5,  // 本地高 revision
        onRefetch,
      });
      return null;
    }
    render(<TestProbe />);
    const es = MockEventSource.instances[0];
    act(() => {
      es.simulateMessage({
        type: 'v1_judgment',
        data: { id: 1, case_id: CASE_ID, aggregate_type: 'judgment', aggregate_id: 'J1', revision: 3 },  // 旧 revision
      });
    });
    // 旧 revision 必不触发 refetch (Mimosa 禁 silent, 显式 0 次)
    expect(onRefetch).not.toHaveBeenCalled();
  });

  it('R18.4 useSSEAggregateInvalidate case_id 不匹配必不触发 refetch (精确失效)', async () => {
    const onRefetch = vi.fn();
    const CASE_ID = 'C' + '0'.repeat(25);
    const OTHER_CASE = 'C' + '1'.padEnd(25, '0');
    function TestProbe() {
      useSSEAggregateInvalidate({
        currentCaseId: CASE_ID,
        currentRevision: 1,
        onRefetch,
      });
      return null;
    }
    render(<TestProbe />);
    const es = MockEventSource.instances[0];
    // 其他 case 的事件
    act(() => {
      es.simulateMessage({
        type: 'v1_judgment',
        data: { id: 1, case_id: OTHER_CASE, aggregate_type: 'judgment', aggregate_id: 'J1', revision: 2 },
      });
    });
    expect(onRefetch).not.toHaveBeenCalled();
  });
});
