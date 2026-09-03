/**
 * SkillStore 单元测试 (v0.8 Phase A, Task A4)
 *
 * 验证意图 (why):
 *  - 商店是 /api/skill-registry 的投影: 列表/筛选/启停/入队四条数据流
 *    必须打到正确的端点 (toggle→enable/disable, run→run), 不能误连 Phase 41
 *    的 /api/skills。
 *  - 筛选语义: category 服务端重拉, type/状态/搜索本地过滤 — 用户切筛选
 *    不能误发多余请求 (category 除外), 也不能让后端过滤逻辑漂移到前端。
 *  - run 是预注册态: 成功只入队 (ticket 回显), 409/429 的错误信封
 *    (detail.message) 必须转译成人话 — "未启用→先启用", "频繁→稍后再试"。
 *  - 启停有二次确认, 防误触 (安全运营技能启停是可观测行为变更)。
 *  - 20 卡片网格 + memo: 大列表渲染稳定性 (rerender 不丢卡片)。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SkillStore } from './SkillStore';
import { apiFetch, postJSON } from '../../lib/api';
import { SkillCategory, SkillSummary, SkillTypeCode } from '../../types/skill';

vi.mock('../../lib/api', () => ({
  apiFetch: vi.fn(),
  postJSON: vi.fn(),
}));

/* ---------- fake 数据工厂: 20 条, category/type/enabled 均匀分布 ---------- */

const CATEGORY_CYCLE: SkillCategory[] = ['operations', 'compliance', 'analysis', 'report'];
const TYPE_CYCLE: SkillTypeCode[] = ['A', 'B', 'C', 'D'];

function makeSkill(i: number): SkillSummary {
  const padded = String(i).padStart(2, '0');
  return {
    id: `skill-${padded}`,
    name: `技能 ${padded}`,
    desc: `第 ${i} 号技能的描述, 用于本地搜索过滤`,
    category: CATEGORY_CYCLE[i % 4],
    skill_type: TYPE_CYCLE[i % 4],
    runner: 'python',
    timeout_seconds: 60,
    feature_gate: null,
    default_enabled: i % 2 === 0,
    enabled: i % 2 === 0,
    has_prompt: i % 4 >= 2,
  };
}

const SKILLS = Array.from({ length: 20 }, (_, i) => makeSkill(i));

function cardCount(): number {
  return screen.queryAllByTestId(/^skill-card-/).length;
}

describe('SkillStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockResolvedValue(SKILLS);
    vi.mocked(postJSON).mockResolvedValue({ enabled: true });
    window.confirm = vi.fn(() => true);
  });

  it('renders 20 skill cards and fetches the registry list (初始 GET 无 category 参数)', async () => {
    render(<SkillStore />);
    expect(await screen.findAllByTestId(/^skill-card-/)).toHaveLength(20);
    expect(vi.mocked(apiFetch)).toHaveBeenCalledWith('/api/skill-registry', { skipLoading: true });
  });

  it('category filter triggers server-side refetch with ?category= (类别走服务端)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);
    vi.mocked(apiFetch).mockClear();

    fireEvent.change(screen.getByLabelText('类别筛选'), { target: { value: 'operations' } });
    await waitFor(() => {
      expect(vi.mocked(apiFetch)).toHaveBeenCalledWith('/api/skill-registry?category=operations', {
        skipLoading: true,
      });
    });
  });

  it('type filter narrows locally to A-type cards (类型本地过滤, 不重发请求)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);
    const callsBefore = vi.mocked(apiFetch).mock.calls.length;

    fireEvent.change(screen.getByLabelText('类型筛选'), { target: { value: 'A' } });
    // 20 条中 i%4===0 共 5 条 A 类
    await waitFor(() => expect(cardCount()).toBe(5));
    expect(vi.mocked(apiFetch).mock.calls.length).toBe(callsBefore);
  });

  it('status filter shows only enabled skills (已启用 → 10 张)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.change(screen.getByLabelText('状态筛选'), { target: { value: 'enabled' } });
    await waitFor(() => expect(cardCount()).toBe(10));
  });

  it('search filter matches name (搜索「05」只剩 1 张)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.change(screen.getByLabelText('搜索技能'), { target: { value: '05' } });
    await waitFor(() => expect(cardCount()).toBe(1));
    expect(screen.getByTestId('skill-card-skill-05')).toBeInTheDocument();
  });

  it('search with no match shows filtered-empty hint (数据在但筛空)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.change(screen.getByLabelText('搜索技能'), { target: { value: '不存在的关键词' } });
    await waitFor(() => expect(screen.getByText('没有匹配的技能，请调整筛选条件')).toBeInTheDocument());
    expect(cardCount()).toBe(0);
  });

  it('shows loading state while the list request is in flight', () => {
    vi.mocked(apiFetch).mockImplementation(() => new Promise(() => {}));
    render(<SkillStore />);
    expect(screen.getByText('技能清单加载中…')).toBeInTheDocument();
    expect(cardCount()).toBe(0);
  });

  it('shows error message with retry when the list request rejects', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('后端连接失败'));
    render(<SkillStore />);
    expect(await screen.findByRole('alert')).toHaveTextContent('后端连接失败');
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  it('shows empty state when the registry returns no skills', async () => {
    vi.mocked(apiFetch).mockResolvedValue([]);
    render(<SkillStore />);
    expect(await screen.findByText('暂无已注册技能')).toBeInTheDocument();
  });

  it('toggle posts to the enable endpoint for a disabled skill (走 /enable 而非 /api/skills)', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    // skill-01: i=1 → enabled=false → 开关 aria-label 为「启用技能 技能 01」
    fireEvent.click(screen.getByRole('switch', { name: '启用技能 技能 01' }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => {
      expect(vi.mocked(postJSON)).toHaveBeenCalledWith('/api/skill-registry/skill-01/enable', {});
    });
    // 成功 → 内联提示 + refresh (列表重拉)
    expect(await screen.findByRole('status')).toHaveTextContent('「技能 01」已启用');
    await waitFor(() => {
      expect(vi.mocked(apiFetch).mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('toggle confirm cancelled → no request is sent (二次确认防误触)', async () => {
    window.confirm = vi.fn(() => false);
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.click(screen.getByRole('switch', { name: '启用技能 技能 01' }));
    expect(window.confirm).toHaveBeenCalled();
    expect(vi.mocked(postJSON)).not.toHaveBeenCalled();
  });

  it('run success shows queued notice with ticket id (预注册态: 只入队)', async () => {
    vi.mocked(postJSON).mockResolvedValue({ ticket_id: 'tg-test-123' });
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.click(screen.getByRole('button', { name: '跑一次 技能 00' }));
    expect(await screen.findByRole('status')).toHaveTextContent('已加入执行队列');
    expect(screen.getByRole('status')).toHaveTextContent('tg-test-123');
    expect(vi.mocked(postJSON)).toHaveBeenCalledWith('/api/skill-registry/skill-00/run', {
      inputs: null,
    });
  });

  it('run 409 (SKILL_DISABLED) → 提示需先启用', async () => {
    vi.mocked(postJSON).mockRejectedValue(new Error("skill 'skill-00' 未启用"));
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.click(screen.getByRole('button', { name: '跑一次 技能 00' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('该技能未启用，请先开启后再运行');
  });

  it('run 429 (THROTTLED) → 提示触发过于频繁', async () => {
    vi.mocked(postJSON).mockRejectedValue(new Error('触发过于频繁: 3/60s'));
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    fireEvent.click(screen.getByRole('button', { name: '跑一次 技能 00' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('触发过于频繁，请稍后再试');
  });

  it('memo cards survive rerender without dropping (大列表渲染稳定)', async () => {
    const { rerender } = render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);
    expect(cardCount()).toBe(20);

    rerender(<SkillStore />);
    rerender(<SkillStore />);
    expect(cardCount()).toBe(20);
    // memo 下数据未变, 列表不重拉
    expect(vi.mocked(apiFetch).mock.calls.length).toBe(1);
  });

  it('cards expose accessible names: switch role/aria-checked + labeled action buttons', async () => {
    render(<SkillStore />);
    await screen.findAllByTestId(/^skill-card-/);

    // 每张卡的开关: role=switch + aria-checked (skill-00 enabled → 停用语义 + true)
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(20);
    expect(screen.getByRole('switch', { name: '停用技能 技能 00' })).toHaveAttribute('aria-checked', 'true');

    // 三个快捷操作按钮全部有可访问名称 (跑一次/详情/历史)
    expect(screen.getAllByRole('button', { name: /^跑一次 技能/ })).toHaveLength(20);
    expect(screen.getAllByRole('button', { name: /^详情 技能/ })).toHaveLength(20);
    expect(screen.getAllByRole('button', { name: /^历史 技能/ })).toHaveLength(20);

    // Phase A: 详情/历史目标不存在 → 禁用态
    expect(screen.getByRole('button', { name: '详情 技能 00' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '历史 技能 00' })).toBeDisabled();
  });
});
