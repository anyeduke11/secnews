// KnowledgeHubPage — C3 (DEV-0191) 接真实聚合后测试
// 数据源 = GET /api/knowledge/hub-stats (六源聚合, 逐源容错); fixture 按真实响应形状
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KnowledgeHubPage } from './KnowledgeHubPage';

const STATS = {
  wiki_items: 12,
  wiki_chunks: 48,
  review_total: 30,
  review_due: 5,
  funnel_total: 20,
  queue_pending: 3,
  quality_checked_24h: 10,
  generated_at: '2026-09-16T08:00:00+00:00',
};

function makeFetch(over?: Partial<typeof STATS>) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/knowledge/hub-stats')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...STATS, ...over }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
  });
}

describe('KnowledgeHubPage — 资料库前厅 (/knowledge/khub, C3 真实聚合)', () => {
  let fetchMock: ReturnType<typeof makeFetch>;
  beforeEach(() => {
    fetchMock = makeFetch();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('报头 + 真实端点印章 + 六源统计卡 (hub-stats 聚合真值)', async () => {
    render(<MemoryRouter><KnowledgeHubPage /></MemoryRouter>);
    expect(screen.getByText('资料库前厅')).toBeInTheDocument();
    expect(screen.getByText('数据源: /api/knowledge/hub-stats (真实端点)')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument());
    expect(screen.getByText('48')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText(/到期 5/)).toBeInTheDocument();
    expect(screen.getByText(/generated 2026-09-16 08:00/)).toBeInTheDocument();
  });

  it('六域快捷入口渲染', () => {
    render(<MemoryRouter><KnowledgeHubPage /></MemoryRouter>);
    expect(screen.getByText('编目室')).toBeInTheDocument();
    expect(screen.getByText('知识图谱')).toBeInTheDocument();
    expect(screen.getByText('统一检索')).toBeInTheDocument();
  });

  it('逐源容错: 单源 null → 显示 … 不拖垮整页', async () => {
    vi.stubGlobal('fetch', makeFetch({ queue_pending: undefined, review_due: undefined }));
    render(<MemoryRouter><KnowledgeHubPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument());
    // queue_pending=null → …; 其余源照常
    expect(screen.getByText(/到期 …/)).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('接口失败 → 错误空态 + 重试', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))));
    render(<MemoryRouter><KnowledgeHubPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('聚合统计加载失败')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });
});
