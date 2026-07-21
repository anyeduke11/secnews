// frontend/src/components/codegarden/DependencyGraph.test.tsx
// Phase 2b Task H2 — DependencyGraph 组件测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { DependencyGraph } from './dependency-graph';
import { CgDependency, CgEvent, Playbook } from '../../types/codegarden';

const dep1: CgDependency = {
  id: 'd1',
  source_type: 'project',
  source_id: 'proj-A',
  target_type: 'service',
  target_id: 'svc-X',
  dep_type: 'code',
  metadata: {},
  created_at: '2026-07-20T00:00:00Z',
};

const dep2: CgDependency = {
  ...dep1,
  id: 'd2',
  source_type: 'service',
  source_id: 'svc-X',
  target_type: 'service',
  target_id: 'svc-Y',
  dep_type: 'service',
};

function mockFetchFor(
  deps: CgDependency[] = [],
  events: CgEvent[] = [],
  playbooks: Playbook[] = [],
) {
  return vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
    if (url.startsWith('/api/codegarden/dependencies?')) {
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ items: deps, total: deps.length }),
      } as Response);
    }
    if (url.startsWith('/api/codegarden/events')) {
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ items: events, total: events.length }),
      } as Response);
    }
    if (url === '/api/codegarden/playbooks') {
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ items: playbooks, total: playbooks.length }),
      } as Response);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response);
  });
}

describe('DependencyGraph', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders empty placeholder when no dependencies', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<DependencyGraph />);
    await waitFor(() => {
      expect(screen.getByText(/暂无依赖关系/)).toBeInTheDocument();
    });
  });

  it('renders dependency count in title', async () => {
    vi.stubGlobal('fetch', mockFetchFor([dep1, dep2]));
    render(<DependencyGraph />);
    await waitFor(() => {
      // 标题 "依赖图谱 (2)" 被拆成 '依赖图谱' 和 '(2)', 分别断言
      expect(screen.getByText('依赖图谱')).toBeInTheDocument();
      expect(screen.getByText('(2)')).toBeInTheDocument();
    });
  });

  it('renders SVG nodes when dependencies exist', async () => {
    vi.stubGlobal('fetch', mockFetchFor([dep1, dep2]));
    const { container } = render(<DependencyGraph />);
    await waitFor(() => {
      // SVG 内有 rect 节点
      const rects = container.querySelectorAll('rect');
      expect(rects.length).toBeGreaterThan(0);
    });
  });

  it('renders dependency list below graph', async () => {
    vi.stubGlobal('fetch', mockFetchFor([dep1]));
    render(<DependencyGraph />);
    await waitFor(() => {
      expect(screen.getByText('project:proj-A')).toBeInTheDocument();
      expect(screen.getByText('service:svc-X')).toBeInTheDocument();
    });
  });

  it('renders dep_type label and color legend', async () => {
    vi.stubGlobal('fetch', mockFetchFor([dep1, dep2]));
    render(<DependencyGraph />);
    await waitFor(() => {
      // '代码' 出现在 SVG edge label + 图例, 至少 1 个
      expect(screen.getAllByText('代码').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('服务').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('数据').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders + 添加依赖 button', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<DependencyGraph />);
    expect(screen.getByText(/\+ 添加依赖/)).toBeInTheDocument();
  });

  it('opens add dialog when + button clicked', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<DependencyGraph />);
    fireEvent.click(screen.getByText(/\+ 添加依赖/));
    await waitFor(() => {
      expect(screen.getByText('添加依赖关系')).toBeInTheDocument();
      // 表单字段
      expect(screen.getByText('Source 类型')).toBeInTheDocument();
      expect(screen.getByText('Target 类型')).toBeInTheDocument();
      expect(screen.getByText('依赖类型')).toBeInTheDocument();
    });
  });

  it('renders impact analysis button per dependency card', async () => {
    vi.stubGlobal('fetch', mockFetchFor([dep1]));
    render(<DependencyGraph />);
    await waitFor(() => {
      expect(screen.getByText('影响分析')).toBeInTheDocument();
    });
  });
});
