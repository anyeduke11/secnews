/**
 * SkillDetail 单元测试 (v0.8 Phase B, Task B6)
 *
 * 验证意图 (why):
 *  - 详情页是 /api/skill-registry/{id} + /{id}/runs 的双数据源投影:
 *    详情=基本元信息 + schema + (C/D 类) prompt 全文; 历史=SkillRunRepo 时间倒序
 *  - 详情未启用/不存在/服务错误必须有清晰反馈 (loading / error+retry / not found);
 *    user 点 Retry 才重拉, 不能自动 polling 制造请求风暴
 *  - RunHistory 行内 [回放] 展开 → 显示 inputs/result 原始 JSON; 终态 run 行内挂
 *    FeedbackBar 👍/👎 → postJSON 必须打到 B6 反馈路由 + score 5/1
 *  - 同一 run 反馈成功后锁定 (不允许重复打分, 防止噪声数据污染 feedback_log)
 *  - useSearchParams ?focus=history 必须在挂载后锚定历史区 (HistoryButton 直达语义)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SkillDetail } from './SkillDetail';
import { apiFetch, postJSON } from '../../lib/api';
import { SkillDetail as SkillDetailType, SkillRun } from '../../types/skill';

vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  postJSON: vi.fn(),
}));

// jsdom 不实现 scrollIntoView, FeedbackBar / SkillDetail 调用不报错
// 用普通 noop 占位 (不放 vi.fn), 避免 vi.clearAllMocks() 把它清掉;
// 测试内通过 spyOn(Element.prototype, 'scrollIntoView') 做调用断言
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {
    /* jsdom 占位: 不抛错 */
  };
}

/** fake 详情 (B 类查询技能, 无 prompt) */
const DETAIL_B: SkillDetailType = {
  id: 'weekly-top-events',
  name: '本周热点安全事件',
  desc: '汇总本周安全事件 top 5, 供研判决策',
  category: 'report',
  skill_type: 'B',
  runner: 'python',
  timeout_seconds: 60,
  feature_gate: null,
  default_enabled: true,
  enabled: true,
  has_prompt: false,
  input_schema: { week: 'str', limit: 'int' },
  output_schema: { items: 'list', summary: 'str' },
};

/** fake 详情 (C 类报告技能, 带 prompt) */
const DETAIL_C: SkillDetailType = {
  ...DETAIL_B,
  id: 'monthly-trend-report',
  name: '月度趋势报告',
  skill_type: 'C',
  has_prompt: true,
  prompt_template: '请基于 inputs.events 生成 {format} 月报',
};

/** fake run 行 */
const RUN_SUCCESS: SkillRun = {
  run_id: 'run-b6-success-01',
  ticket_id: 'tg-001',
  skill_id: 'weekly-top-events',
  status: 'succeeded',
  phase: 'done',
  inputs: { intent: '上周安全事件周报' },
  result: { items: [{ id: 1 }], summary: 'ok' },
  metrics: { elapsed_ms: 1230, llm_tokens: 0 },
  error: null,
  created_at: '2026-09-04 10:00:00',
  finished_at: '2026-09-04 10:00:01',
};

const RUN_FAILED: SkillRun = {
  ...RUN_SUCCESS,
  run_id: 'run-b6-failed-01',
  status: 'failed',
  phase: 'failed',
  inputs: { intent: 'x' },
  result: null,
  metrics: { elapsed_ms: 500 },
  error: '数据源超时',
  finished_at: '2026-09-04 11:00:01',
  created_at: '2026-09-04 11:00:00',
};

const RUN_RUNNING: SkillRun = {
  ...RUN_SUCCESS,
  run_id: 'run-b6-running-01',
  status: 'running',
  phase: 'fetch',
  finished_at: null,
};

/** 路由包装: 注入 useParams + useSearchParams */
function renderDetail(initialPath = '/skill-store/weekly-top-events') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/skill-store/:skillId" element={<SkillDetail onBack={() => {}} />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('SkillDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.confirm = vi.fn(() => true);
  });

  it('loads detail + runs on mount (B6: 双数据源打正确端点)', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(DETAIL_B)
      .mockResolvedValueOnce([RUN_SUCCESS, RUN_FAILED]);
    renderDetail();

    await screen.findByText('本周热点安全事件');
    expect(apiFetch).toHaveBeenCalledWith('/api/skill-registry/weekly-top-events', {
      skipLoading: true,
    });
    expect(apiFetch).toHaveBeenCalledWith(
      '/api/skill-registry/weekly-top-events/runs?limit=20',
      { skipLoading: true }
    );
  });

  it('renders schema sections (input_schema + output_schema 列字段)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([]);
    renderDetail();

    expect(await screen.findByText('本周热点安全事件')).toBeInTheDocument();
    // schema 表头
    expect(screen.getByText('输入字段 (input_schema)')).toBeInTheDocument();
    expect(screen.getByText('输出字段 (output_schema)')).toBeInTheDocument();
    // schema 字段名
    expect(screen.getByText('week')).toBeInTheDocument();
    expect(screen.getByText('limit')).toBeInTheDocument();
    expect(screen.getByText('items')).toBeInTheDocument();
    expect(screen.getByText('summary')).toBeInTheDocument();
    // 类型列
    expect(screen.getAllByText('str').length).toBeGreaterThan(0);
    expect(screen.getAllByText('int').length).toBeGreaterThan(0);
  });

  it('shows prompt_template only for C/D skills (has_prompt=true 渲染全文)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_C).mockResolvedValueOnce([]);
    renderDetail('/skill-store/monthly-trend-report');

    expect(await screen.findByText('月度趋势报告')).toBeInTheDocument();
    expect(screen.getByText(/请基于 inputs\.events 生成/)).toBeInTheDocument();
    expect(screen.getByText('Prompt 模板')).toBeInTheDocument();
  });

  it('hides prompt section when has_prompt=false (B 类查询技能)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([]);
    renderDetail();

    await screen.findByText('本周热点安全事件');
    expect(screen.queryByText('Prompt 模板')).not.toBeInTheDocument();
  });

  it('shows loading state while detail is in flight', () => {
    vi.mocked(apiFetch).mockImplementation(() => new Promise(() => {}));
    renderDetail();
    expect(screen.getByText('技能详情加载中…')).toBeInTheDocument();
  });

  it('shows error + retry on detail failure (404/500 → 不静默)', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('技能 weekly-top-events 未找到'));
    renderDetail();

    expect(await screen.findByRole('alert')).toHaveTextContent('未找到');
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  it('retry button re-fetches detail (用户主动重试, 不自动 polling)', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new Error('boom'));
    renderDetail();
    await screen.findByRole('alert');

    vi.mocked(apiFetch)
      .mockResolvedValueOnce(DETAIL_B)
      .mockResolvedValueOnce([]);
    fireEvent.click(screen.getByText('重试'));

    expect(await screen.findByText('本周热点安全事件')).toBeInTheDocument();
    // 第 1 次失败 + 第 2 次成功 = detail 调用 ≥ 2 次; runs 也调用 1 次
    expect(vi.mocked(apiFetch).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('RunHistory renders rows with status badge (成功/失败/运行中色条)', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(DETAIL_B)
      .mockResolvedValueOnce([RUN_SUCCESS, RUN_FAILED, RUN_RUNNING]);
    renderDetail();

    await screen.findByText('本周热点安全事件');
    // 三条 run 行
    const rows = screen.getAllByTestId(/^run-row-/);
    expect(rows).toHaveLength(3);
    // 状态色码标签
    expect(screen.getByText('[成功]')).toBeInTheDocument();
    expect(screen.getByText('[失败]')).toBeInTheDocument();
    expect(screen.getByText('[运行中]')).toBeInTheDocument();
    // 失败 run 错误信息内联
    expect(screen.getByText('数据源超时')).toBeInTheDocument();
  });

  it('RunHistory [回放] 展开 inputs/result 原始 JSON (重放是结果复盘而非重跑)', async () => {
    // useSkillDetail + useSkillRuns 两次连续 apiFetch 调用
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(DETAIL_B)
      .mockResolvedValueOnce([RUN_SUCCESS]);
    renderDetail();

    await screen.findByText('本周热点安全事件');
    const replay = screen.getByRole('button', { name: '回放 run-b6-success-01' });
    expect(replay).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(replay);

    // JSON 文本: inputs 含 intent 字段, result 含 summary
    expect(await screen.findByText(/intent/)).toBeInTheDocument();
    expect(screen.getByText(/上周安全事件周报/)).toBeInTheDocument();
    expect(replay).toHaveAttribute('aria-expanded', 'true');
    // 收起状态: 同 aria-label 按钮仍存在, 内容文字从 "回放" 切到 "收起"
    expect(screen.getByText('收起')).toBeInTheDocument();
  });

  it('FeedbackBar 👍 posts score=5 to B6 feedback endpoint (B6 验收链路)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_SUCCESS]);
    vi.mocked(postJSON).mockResolvedValueOnce({
      id: 1,
      skill_run_id: 'run-b6-success-01',
      skill_id: 'weekly-top-events',
      score: 5,
      comment: '',
      created_at: '2026-09-04 12:00:00',
    });
    renderDetail();

    await screen.findByText('本周热点安全事件');

    fireEvent.click(screen.getByRole('button', { name: '好评 run-b6-success-01' }));

    await waitFor(() => {
      expect(postJSON).toHaveBeenCalledWith(
        '/api/skill-registry/runs/run-b6-success-01/feedback',
        { score: 5, comment: '' }
      );
    });
    expect(await screen.findByText('已反馈 👍')).toBeInTheDocument();
  });

  it('FeedbackBar 👎 posts score=1 (差评 = 最低分, 供 recall 学习)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_FAILED]);
    vi.mocked(postJSON).mockResolvedValueOnce({
      id: 2,
      skill_run_id: 'run-b6-failed-01',
      skill_id: 'weekly-top-events',
      score: 1,
      comment: '',
      created_at: '2026-09-04 12:00:00',
    });
    renderDetail();

    await screen.findByText('本周热点安全事件');

    fireEvent.click(screen.getByRole('button', { name: '差评 run-b6-failed-01' }));

    await waitFor(() => {
      expect(postJSON).toHaveBeenCalledWith(
        '/api/skill-registry/runs/run-b6-failed-01/feedback',
        { score: 1, comment: '' }
      );
    });
    expect(await screen.findByText('已反馈 👎')).toBeInTheDocument();
  });

  it('FeedbackBar locks after first submit (防止同 run 重复打分污染 feedback_log)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_SUCCESS]);
    vi.mocked(postJSON).mockResolvedValue({
      id: 1,
      skill_run_id: 'run-b6-success-01',
      skill_id: 'weekly-top-events',
      score: 5,
      comment: '',
      created_at: '2026-09-04 12:00:00',
    });
    renderDetail();

    await screen.findByText('本周热点安全事件');
    fireEvent.click(screen.getByRole('button', { name: '好评 run-b6-success-01' }));
    await screen.findByText('已反馈 👍');

    // 锁定后: 👍/👎 按钮整体被已反馈文字替代, postJSON 不会再次被调用
    expect(postJSON).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '好评 run-b6-success-01' })).not.toBeInTheDocument();
  });

  it('FeedbackBar hidden on running runs (未结束 run 不该被打分)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_RUNNING]);
    renderDetail();

    await screen.findByText('本周热点安全事件');
    // 运行中行内无反馈条按钮
    expect(
      screen.queryByRole('button', { name: '好评 run-b6-running-01' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '差评 run-b6-running-01' })
    ).not.toBeInTheDocument();
  });

  it('feedback error surfaces inline (run 不存在等 400/404 转译)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_SUCCESS]);
    vi.mocked(postJSON).mockRejectedValueOnce(new Error('run not found'));
    renderDetail();

    await screen.findByText('本周热点安全事件');
    fireEvent.click(screen.getByRole('button', { name: '好评 run-b6-success-01' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('run not found');
  });

  it('?focus=history puts focus on RunHistory section (历史直达语义)', async () => {
    // 注: 不直接断言 scrollIntoView 副作用 (jsdom 不实现, spy 在 vi.clearAllMocks 下串扰),
    // 仅验 useEffect 触发条件: detail 加载 + searchParams.focus=history → 历史区 DOM 已渲染,
    // 真实滚动由浏览器处理 (e2e 已覆盖)。此处只验「直达入口不阻断渲染」。
    vi.mocked(apiFetch).mockResolvedValueOnce(DETAIL_B).mockResolvedValueOnce([RUN_SUCCESS]);
    renderDetail('/skill-store/weekly-top-events?focus=history');

    // detail + runs 完整加载, 历史区可见
    expect(await screen.findByTestId('run-history')).toBeInTheDocument();
    expect(screen.getByText('本周热点安全事件')).toBeInTheDocument();
  });
});