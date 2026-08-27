/**
 * Phase13PlanningPanel.test.tsx — Phase 13 规划动作面板测试
 *
 * 覆盖: KnowledgePlanningPanel
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { KnowledgePlanningPanel } from './KnowledgePlanningPanel';

const mockActions = [
  {
    id: 1,
    item_id: 'item-001',
    action_type: 'read',
    priority: 8,
    title: '阅读《Zero Trust 架构》',
    description: '该条目处于原始阶段，建议先阅读了解内容',
    current_stage: 'kl:raw',
    target_stage: 'kl:refine',
    status: 'pending',
    created_at: '2026-07-31T08:00:00Z',
    completed_at: null,
    dismissed_at: null,
  },
  {
    id: 2,
    item_id: 'item-002',
    action_type: 'link',
    priority: 5,
    title: '关联《LLM 安全实践》到概念图',
    description: '该条目包含可关联的 AI 安全概念',
    current_stage: 'kl:refine',
    target_stage: 'kl:link',
    status: 'pending',
    created_at: '2026-07-31T07:00:00Z',
    completed_at: null,
    dismissed_at: null,
  },
];

describe('KnowledgePlanningPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('test_planning_panel_renders', async () => {
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/kl/planning-actions')) {
        return new Response(
          JSON.stringify(mockActions),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;

    render(<KnowledgePlanningPanel />);

    // 标题
    await waitFor(() => {
      expect(screen.getByText('规划动作')).toBeInTheDocument();
    });

    // 待办计数
    await waitFor(() => {
      expect(screen.getByText('2 项待办')).toBeInTheDocument();
    });

    // 条目内容
    await waitFor(() => {
      expect(screen.getByText('阅读《Zero Trust 架构》')).toBeInTheDocument();
      expect(screen.getByText('关联《LLM 安全实践》到概念图')).toBeInTheDocument();
    });

    // 优先级徽章
    await waitFor(() => {
      expect(screen.getByText('P8')).toBeInTheDocument();
      expect(screen.getByText('P5')).toBeInTheDocument();
    });

    // 阶段流转 (精炼出现 2 次: 第一个 action 的 target + 第二个 action 的 current)
    await waitFor(() => {
      expect(screen.getByText('原始')).toBeInTheDocument();
      const refined = screen.getAllByText('精炼');
      expect(refined.length).toBe(2);
    });
  });

  it('test_planning_panel_empty', async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify([]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as any;

    render(<KnowledgePlanningPanel />);

    await waitFor(() => {
      expect(screen.getByText('暂无待办规划动作，系统将在下次检查时自动生成')).toBeInTheDocument();
    });
  });

  it('test_planning_panel_mark_complete', async () => {
    let putCalled = false;
    global.fetch = vi.fn(async (url: any, opts?: any) => {
      const u = typeof url === 'string' ? url : url.url;
      const method = opts?.method || 'GET';
      if (u.includes('/api/kl/planning-actions') && method === 'GET') {
        return new Response(
          JSON.stringify(mockActions),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      // PUT 标记完成
      if (u.includes('/api/kl/planning-actions') && method === 'PUT') {
        putCalled = true;
        return new Response(
          JSON.stringify({ status: 'ok' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;

    render(<KnowledgePlanningPanel />);

    // 等待数据加载
    await waitFor(() => {
      expect(screen.getByText('阅读《Zero Trust 架构》')).toBeInTheDocument();
    });

    // 点击"标记完成"按钮
    const completeButtons = screen.getAllByTitle('标记完成');
    fireEvent.click(completeButtons[0]);

    // 验证 PUT API 调用
    await waitFor(() => {
      expect(putCalled).toBe(true);
    });

    // 验证 API 调用了正确的 URL
    await waitFor(() => {
      const putCalls = (global.fetch as any).mock.calls.filter(
        (c: any[]) => c[1]?.method === 'PUT' && typeof c[0] === 'string' && c[0].includes('/api/kl/planning-actions')
      );
      expect(putCalls.length).toBeGreaterThanOrEqual(1);
      const putUrl = putCalls[0][0] as string;
      expect(putUrl).toContain('/api/kl/planning-actions/1/status');
    });
  });
});