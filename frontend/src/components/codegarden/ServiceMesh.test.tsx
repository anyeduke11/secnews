// frontend/src/components/codegarden/ServiceMesh.test.tsx
// Phase 2b Task H2 — ServiceMesh 组件测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ServiceMesh } from './service-mesh';
import { CgService } from '../../types/codegarden';

// 服务样本
const sampleService: CgService = {
  id: 'svc-1',
  project_id: null,
  name: 'test-api',
  namespace: 'default',
  type: 'http',
  runtime: 'docker',
  status: 'running',
  endpoint_host: '127.0.0.1',
  endpoint_port: 8001,
  endpoint_domain: null,
  health_check_type: 'http',
  health_check_path: '/health',
  health_check_interval: 30,
  cpu_limit: null,
  memory_limit: null,
  dependencies: [],
  env_vars: {},
  created_at: '2026-07-20T00:00:00Z',
  last_checked_at: null,
};

const errorService: CgService = {
  ...sampleService,
  id: 'svc-2',
  name: 'broken-svc',
  status: 'error',
  runtime: 'pm2',
  endpoint_port: 9000,
  dependencies: ['svc-1'],
};

function mockFetchOnce(items: CgService[] = [], total = 0) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.startsWith('/api/codegarden/services?')) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ items, total, limit: 500, offset: 0 }),
      } as Response);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response);
  });
}

describe('ServiceMesh', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders loading placeholder on first mount', async () => {
    const mockFetch = mockFetchOnce([sampleService], 1);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    // 初次渲染 loading
    expect(screen.getByText('加载中…')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('加载中…')).not.toBeInTheDocument();
    });
  });

  it('renders service cards when fetch returns items', async () => {
    const mockFetch = mockFetchOnce([sampleService, errorService], 2);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      expect(screen.getByText('test-api')).toBeInTheDocument();
      expect(screen.getByText('broken-svc')).toBeInTheDocument();
    });
    // 总数
    expect(screen.getByText(/共 2/)).toBeInTheDocument();
  });

  it('shows error message when fetch fails', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network down'));
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      expect(screen.getByText(/Network down/)).toBeInTheDocument();
    });
  });

  it('shows empty placeholder when no services', async () => {
    const mockFetch = mockFetchOnce([], 0);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      expect(screen.getByText(/暂无服务/)).toBeInTheDocument();
    });
  });

  it('renders runtime + status badges per card', async () => {
    const mockFetch = mockFetchOnce([errorService], 1);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      // runtime 'pm2' 既是 <option> 又是 card badge, 至少出现 2 次
      expect(screen.getAllByText('pm2').length).toBeGreaterThanOrEqual(2);
      // '异常' 同样既是 <option> 又是 badge
      expect(screen.getAllByText('异常').length).toBeGreaterThanOrEqual(2);
    });
    // 端口 :9000 已渲染 — 整个 document body 应包含 9000 文本
    await waitFor(() => {
      expect(document.body.textContent).toContain('9000');
    });
  });

  it('shows dependency count when service has dependencies', async () => {
    const mockFetch = mockFetchOnce([errorService], 1);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      // 依赖 1 项
      expect(screen.getByText(/依赖 1 项/)).toBeInTheDocument();
    });
  });

  it('opens detail dialog when card is clicked', async () => {
    const mockFetch = mockFetchOnce([sampleService], 1);
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      expect(screen.getByText('test-api')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('test-api'));
    // 详情弹窗标题
    await waitFor(() => {
      expect(screen.getAllByText('test-api').length).toBeGreaterThan(1);
    });
    // 元数据 tab + 日志 tab + 指标 tab
    expect(screen.getByText('元数据')).toBeInTheDocument();
    expect(screen.getByText('日志')).toBeInTheDocument();
    expect(screen.getByText('指标')).toBeInTheDocument();
  });

  it('triggers scan API when scan button clicked', async () => {
    const mockFetch = mockFetchOnce([sampleService], 1);
    // 给 scan 调用一个独立的 mock 实现
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/codegarden/services/scan' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ scanned: 3, created: 1, updated: 1 }),
        } as Response);
      }
      if (url.startsWith('/api/codegarden/services')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ items: [sampleService], total: 1, limit: 500, offset: 0 }),
        } as Response);
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response);
    });
    vi.stubGlobal('fetch', mockFetch);
    render(<ServiceMesh />);
    await waitFor(() => {
      expect(screen.getByText('test-api')).toBeInTheDocument();
    });
    // 找到放大镜图标按钮（title="扫描本地服务"）
    const scanBtn = screen.getByTitle('扫描本地服务');
    fireEvent.click(scanBtn);
    await waitFor(() => {
      expect(screen.getByText(/扫描完成: 新增 1 \/ 更新 1 \/ 共 3/)).toBeInTheDocument();
    });
  });
});
