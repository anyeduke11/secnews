/**
 * Phase13ModeComponents.test.tsx — Phase 13 模式组件测试
 *
 * 覆盖: LifecycleProgress, BriefingMode, ScanMode, AlertMode
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LifecycleProgress, ALL_STAGES, STAGE_LABELS, STAGE_COLORS } from './LifecycleProgress';
import { BriefingMode } from './BriefingMode';
import { ScanMode } from './ScanMode';
import { AlertMode } from './AlertMode';

// ---------------------------------------------------------------------------
// LifecycleProgress
// ---------------------------------------------------------------------------

describe('LifecycleProgress', () => {
  it('test_lifecycle_progress_renders', () => {
    render(<LifecycleProgress currentStage="kl:raw" />);
    // 5 个阶段标签都应渲染
    for (const label of Object.values(STAGE_LABELS)) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('test_lifecycle_progress_colors', () => {
    const { container } = render(<LifecycleProgress currentStage="kl:raw" />);
    const progressEl = container.querySelector('[data-lifecycle-progress]');
    expect(progressEl).toBeInTheDocument();
    // 每个阶段应有对应的颜色
    for (const stage of ALL_STAGES) {
      expect(STAGE_COLORS[stage]).toBeDefined();
      expect(STAGE_COLORS[stage]).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it('test_lifecycle_progress_current_stage', () => {
    const { container } = render(<LifecycleProgress currentStage="kl:link" />);
    const progressEl = container.querySelector('[data-lifecycle-progress]');
    expect(progressEl).toHaveAttribute('data-current-stage', 'kl:link');
    // 当前阶段标签应包含 aria-label 提示
    const currentLabel = `${STAGE_LABELS['kl:link']}（当前）`;
    expect(screen.getByLabelText(currentLabel)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BriefingMode
// ---------------------------------------------------------------------------

describe('BriefingMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      // 知识条目接口
      if (u.includes('/api/knowledge/items')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: '1',
                title: '今日发布文章',
                source: 'cubox',
                source_url: 'https://example.com/1',
                domain: 'security',
                topic: null,
                tags: ['安全', 'AI'],
                concepts: ['LLM'],
                mastered: 85,
                lifecycle: 'kl:publish',
                ingested_at: '2026-07-31T08:00:00Z',
                updated_at: '2026-07-31T08:00:00Z',
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      // 数据源健康状态接口
      if (u.includes('/api/sources/health')) {
        return new Response(
          JSON.stringify({
            sources: [
              { category: 'secnews', source_name: 'AI Hot', status: 'active', total_items: 120, last_checked_at: null, last_error: null },
              { category: 'secnews', source_name: '安全客', status: 'active', total_items: 80, last_checked_at: null, last_error: null },
              { category: 'secnews', source_name: 'FreeBuf', status: 'stale', total_items: 200, last_checked_at: null, last_error: 'timeout' },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('test_briefing_mode_renders', async () => {
    render(<MemoryRouter><BriefingMode /></MemoryRouter>);
    // 标题区域
    await waitFor(() => {
      expect(screen.getByText('简报模式 · 今日知识发布')).toBeInTheDocument();
    });
    // 健康状态 (含 ● 前缀)
    await waitFor(() => {
      expect(screen.getByText(/2 活跃/)).toBeInTheDocument();
      expect(screen.getByText(/1 停滞/)).toBeInTheDocument();
    });
    // 发布条目
    await waitFor(() => {
      expect(screen.getByText('今日发布文章')).toBeInTheDocument();
    });
  });

  it('test_briefing_mode_empty', async () => {
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/knowledge/items')) {
        return new Response(
          JSON.stringify({ items: [], total: 0 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (u.includes('/api/sources/health')) {
        return new Response(
          JSON.stringify({ sources: [] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;

    render(<MemoryRouter><BriefingMode /></MemoryRouter>);
    await waitFor(() => {
      expect(screen.getByText('今日暂无已发布条目')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// ScanMode
// ---------------------------------------------------------------------------

describe('ScanMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.includes('/api/knowledge/items')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: '1',
                title: '扫描测试条目',
                source: 'secnews',
                source_url: 'https://example.com/scan',
                domain: 'security',
                topic: null,
                type: 'article',
                difficulty: 'medium',
                tags: ['CVE', '漏洞'],
                concepts: [],
                mastered: 60,
                lifecycle: 'kl:refine',
                ingested_at: '2026-07-30T10:00:00Z',
                updated_at: '2026-07-30T10:00:00Z',
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('test_scan_mode_renders', async () => {
    render(<ScanMode />);
    // 标题
    await waitFor(() => {
      expect(screen.getByText('快速扫描')).toBeInTheDocument();
    });
    // 条目渲染
    await waitFor(() => {
      expect(screen.getByText('扫描测试条目')).toBeInTheDocument();
    });
    // 筛选控件
    await waitFor(() => {
      expect(screen.getByLabelText('按分类筛选')).toBeInTheDocument();
      expect(screen.getByLabelText('按生命周期筛选')).toBeInTheDocument();
      expect(screen.getByLabelText('按标签筛选')).toBeInTheDocument();
    });
    // 时间范围按钮组
    await waitFor(() => {
      expect(screen.getByLabelText('时间范围')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// AlertMode
// ---------------------------------------------------------------------------

describe('AlertMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any, opts?: any) => {
      const u = typeof url === 'string' ? url : url.url;
      const method = opts?.method || 'GET';

      // AlertMode 的未读计数
      if (u.includes('/api/alerts/v2/unread-count')) {
        return new Response(
          JSON.stringify({ count: 3 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      // AlertCenter 的告警列表
      if (u.includes('/api/alerts/v2') && method === 'GET') {
        return new Response(
          JSON.stringify({
            count: 3,
            items: [
              { id: 1, rule_type: 'tech_stack_cve', title: '告警 1', description: '描述', severity: 'high', source: 'CVE', source_url: null, status: 'unread', created_at: '2026-07-31T10:00:00Z' },
              { id: 2, rule_type: 'critical_cve', title: '告警 2', description: '描述', severity: 'critical', source: 'CVE', source_url: null, status: 'unread', created_at: '2026-07-31T09:00:00Z' },
              { id: 3, rule_type: 'bid_match', title: '告警 3', description: '描述', severity: 'medium', source: 'bid', source_url: null, status: 'unread', created_at: '2026-07-31T08:00:00Z' },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('test_alert_mode_renders', async () => {
    render(<AlertMode />);
    // 红色横幅 + AlertCenter 中都包含未读计数文本
    await waitFor(() => {
      const matches = screen.getAllByText('3 条未读告警');
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
    // AlertCenter 标题
    await waitFor(() => {
      expect(screen.getByText('告警中心')).toBeInTheDocument();
    });
  });

  it('test_alert_mode_badge', async () => {
    render(<AlertMode />);
    // AlertMode 横幅中的红色圆角徽章 (背景色 #dc2626 的 inline-flex 元素)
    await waitFor(() => {
      const badges = screen.getAllByText('3').filter(
        el => el.closest('[style*="background-color: rgb(220, 38, 38)"]')
      );
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });
});