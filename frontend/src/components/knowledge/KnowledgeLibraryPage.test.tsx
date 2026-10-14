// KnowledgeLibraryPage — C1 (DEV-0189) 接真实数据后测试
// 数据源 = GET /api/knowledge/items (真实端点); fixture 按 KnowledgeItem.to_dict 真实形状
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KnowledgeLibraryPage } from './KnowledgeLibraryPage';

/** 真实 to_dict 字段形状的编目行 */
function itemOf(id: string, over: Partial<Record<string, unknown>> = {}) {
  return {
    id,
    title: `条目 ${id} 的标题`,
    source: 'SecWiki',
    source_url: 'https://example.com/a',
    domain: 'security',
    topic: '零信任',
    type: 'analysis',
    difficulty: 'intermediate',
    tags: '[]',
    concepts: '[]',
    mastery: 2,
    compiled: 1,
    lifecycle: 'active',
    news_type: null,
    tech_stack: null,
    ingested_at: '2026-09-10T08:00:00+00:00',
    updated_at: '2026-09-10T08:00:00+00:00',
    ...over,
  };
}

function makeFetch(overrides?: { items?: unknown[]; total?: number }) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/knowledge/topics')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ topics: ['零信任', '供应链'] }) } as Response);
    }
    if (url.includes('/api/knowledge/items')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          items: overrides?.items ?? [itemOf('k01'), itemOf('k02', { domain: 'ai', mastery: 4 })],
          total: overrides?.total ?? 2,
        }),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('KnowledgeLibraryPage — 编目室 (/knowledge/library, C1 真实数据)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('报头 + 真实端点印章 + 编目行渲染 (标题/领域/掌握度/收录日期)', async () => {
    render(<MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>);
    expect(screen.getByText('编目室')).toBeInTheDocument();
    expect(screen.getByText('数据源: /api/knowledge/items (真实端点)')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('条目 k01 的标题')).toBeInTheDocument());
    expect(screen.getByText('k01')).toBeInTheDocument();
    expect(screen.getByText('2/5')).toBeInTheDocument();
    expect(screen.getAllByText('2026-09-10').length).toBe(2);
    expect(screen.getByText(/域内 2 条/)).toBeInTheDocument();
  });

  it('领域筛选: select 变更触发带 domain 参数的请求并回到第 1 页', async () => {
    render(<MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('条目 k01 的标题')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('领域'), { target: { value: 'security' } });
    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(c => {
        const u = String(c[0]);
        return u.includes('/api/knowledge/items') && u.includes('domain=security');
      });
      expect(calls.length).toBeGreaterThanOrEqual(1);
    });
    // 主题下拉随领域联动拉取 topics
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('topics?domain=security'))).toBe(true);
  });

  it('翻页: 满 50 条时下一页可用, offset 随页码推进', async () => {
    const fiftyOne = Array.from({ length: 51 }, (_, i) => itemOf(`k${String(i).padStart(2, '0')}`));
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/knowledge/topics')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ topics: [] }) } as Response);
      }
      if (url.includes('/api/knowledge/items')) {
        const offset = Number(new URL(url, 'http://x').searchParams.get('offset') ?? 0);
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: fiftyOne.slice(offset, offset + 50), total: 51 }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });

    render(<MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(document.querySelectorAll('.ed-table tbody tr').length).toBe(50));
    const next = screen.getByRole('button', { name: '下一页' });
    expect(next).toBeEnabled();
    fireEvent.click(next);
    await waitFor(() => expect(document.querySelectorAll('.ed-table tbody tr').length).toBe(1));
    // 第 2 页请求 offset=50
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('offset=50'))).toBe(true);
    // 第 2 页只有 1 条 (<50) → 下一页禁用
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  });

  it('空结果 → 显式空态 (不伪造数据)', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/knowledge/topics')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ topics: [] }) } as Response);
      }
      if (url.includes('/api/knowledge/items')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [], total: 0 }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    render(<MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('该筛选条件下暂无编目条目')).toBeInTheDocument());
  });

  it('接口失败 → 错误空态 + 口径提示, 不白屏', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'boom' }) } as Response)));
    render(<MemoryRouter><KnowledgeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('编目清单加载失败')).toBeInTheDocument());
  });
});
