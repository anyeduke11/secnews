// frontend/src/components/codegarden/ResourceHub.test.tsx
// Phase 2b Task H2 — ResourceHub 组件测试（含 PortPool）
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ResourceHub } from './resource-hub';
import { CgResource } from '../../types/codegarden';

const allocatedPort: CgResource = {
  id: 'r1',
  type: 'port',
  value: '8001',
  status: 'allocated',
  owner_service_id: 'svc-1',
  owner_project_id: null,
  metadata: {},
  reserved_until: null,
  created_at: '2026-07-20T00:00:00Z',
};

const freePort: CgResource = {
  ...allocatedPort,
  id: 'r2',
  value: '8002',
  status: 'free',
  owner_service_id: null,
};

const domain: CgResource = {
  id: 'r3',
  type: 'domain',
  value: 'api.test.local',
  status: 'allocated',
  owner_service_id: 'svc-1',
  owner_project_id: null,
  metadata: {},
  reserved_until: null,
  created_at: '2026-07-20T00:00:00Z',
};

function mockFetchFor(items: CgResource[]) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.startsWith('/api/codegarden/resources')) {
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ items, total: items.length, limit: 500, offset: 0 }),
      } as Response);
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response);
  });
}

describe('ResourceHub', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders 4 tabs (端口/域名/环境模板/卷)', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<ResourceHub />);
    expect(screen.getByText('端口')).toBeInTheDocument();
    expect(screen.getByText('域名')).toBeInTheDocument();
    expect(screen.getByText('环境模板')).toBeInTheDocument();
    expect(screen.getByText('存储卷')).toBeInTheDocument();
  });

  it('renders PortPool grid when on port tab', async () => {
    vi.stubGlobal('fetch', mockFetchFor([allocatedPort, freePort]));
    render(<ResourceHub />);
    await waitFor(() => {
      // 默认 tab = port, 显示端口范围标识
      expect(screen.getByText('8000-8019')).toBeInTheDocument();
    });
  });

  it('shows legend colors for port statuses', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<ResourceHub />);
    await waitFor(() => {
      expect(screen.getByText('空闲')).toBeInTheDocument();
      expect(screen.getByText('已分配')).toBeInTheDocument();
      expect(screen.getByText('预留')).toBeInTheDocument();
      expect(screen.getByText('保护(8898)')).toBeInTheDocument();
    });
  });

  it('renders allocate buttons on port tab', async () => {
    vi.stubGlobal('fetch', mockFetchFor([]));
    render(<ResourceHub />);
    await waitFor(() => {
      expect(screen.getByText('分配指定端口')).toBeInTheDocument();
      expect(screen.getByText('自动分配')).toBeInTheDocument();
    });
  });

  it('renders domain cards when switched to domain tab', async () => {
    vi.stubGlobal('fetch', mockFetchFor([domain]));
    const { container } = render(<ResourceHub />);
    await waitFor(() => {
      expect(screen.getByText('8000-8019')).toBeInTheDocument();
    });
    // 切到 domain tab
    const domainTab = screen.getByText('域名');
    (domainTab as HTMLElement).click();
    await waitFor(() => {
      expect(screen.getByText('api.test.local')).toBeInTheDocument();
    });
  });

  it('shows total count badge', async () => {
    vi.stubGlobal('fetch', mockFetchFor([allocatedPort, freePort]));
    render(<ResourceHub />);
    await waitFor(() => {
      expect(screen.getByText(/共 2/)).toBeInTheDocument();
    });
  });
});
