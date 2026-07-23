// frontend/src/components/DeepReadView.test.tsx
// v1.7 Phase 4 — DeepReadView 组件测试
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// Mock useGoHome — 避免 jsdom 跳转问题
vi.mock('../hooks/useGoHome', () => ({
  useGoHome: () => () => {},
}));

// Mock useAnnotations — NotePanel 依赖
vi.mock('../hooks/useAnnotations', () => ({
  useAnnotations: vi.fn(() => ({
    items: [],
    loading: false,
    load: vi.fn(),
    add: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  })),
}));

// Mock NoteEditor — 避免依赖复杂子组件
vi.mock('./shared/NoteEditor', () => ({
  NoteEditor: ({ entityType, entityId }: { entityType: string; entityId: string }) => (
    <div data-testid="note-editor">
      NoteEditor for {entityType}/{entityId}
    </div>
  ),
}));

import { DeepReadView } from './DeepReadView';
import { useAnnotations } from '../hooks/useAnnotations';

const mockArticle = {
  id: 'h1',
  title: 'FastAPI 0.100 发布',
  summary: '新增 lifespan + Better ASGI 支持',
  source: 'fastapi.tiangolo.com',
  url: 'https://fastapi.tiangolo.com/',
  category: 'ai',
  published_at: '2026-07-23T10:00:00+00:00',
  score: 88,
};

const mockRecommendations = {
  version: '1.7.0',
  entity_type: 'hotspot',
  entity_id: 'h1',
  items: [
    {
      item: {
        id: 'h2',
        title: 'FastAPI 中间件指南',
        summary: '详解中间件执行顺序与错误处理',
        source: 'freebuf',
        category: 'security',
        ingested_at: '2026-07-22T08:00:00+00:00',
        score: 70,
      },
      score: 2,
      shared_tags: ['fastapi', 'python'],
    },
    {
      item: {
        id: 'h3',
        title: 'Pydantic v2 性能优化',
        summary: 'v2 比 v1 快 5-50x',
        source: 'pydantic.dev',
        category: 'ai',
        ingested_at: '2026-07-22T09:00:00+00:00',
        score: 65,
      },
      score: 1,
      shared_tags: ['python'],
    },
  ],
};

function renderWithRouter(path: string = '/deep/hotspot/h1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/deep/:type/:id" element={<DeepReadView />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('DeepReadView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      // GET /api/hotspots/{id} → 文章详情
      if (u.match(/\/api\/hotspots\/[^/]+$/)) {
        return new Response(JSON.stringify({ item: mockArticle }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // GET /api/recommend/{type}/{id} → 推荐
      if (u.match(/\/api\/recommend\/[^/]+\/[^/]+/)) {
        return new Response(JSON.stringify(mockRecommendations), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      // GET /api/annotations → 空笔记列表
      if (u.startsWith('/api/annotations')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('renders article title and summary after loading', async () => {
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText('FastAPI 0.100 发布')).toBeInTheDocument();
    });
    expect(screen.getByText(/新增 lifespan/)).toBeInTheDocument();
  });

  it('shows source and score metadata', async () => {
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText(/来源: fastapi.tiangolo.com/)).toBeInTheDocument();
    });
    expect(screen.getByText(/★ 88/)).toBeInTheDocument();
  });

  it('renders original link', async () => {
    renderWithRouter();
    await waitFor(() => {
      const link = screen.getByText('原文链接 ↗');
      expect(link).toHaveAttribute('href', 'https://fastapi.tiangolo.com/');
    });
  });

  it('renders RecommendationSidebar with related items', async () => {
    renderWithRouter();
    // 验收 2: 推荐侧栏显示相关条目
    await waitFor(() => {
      expect(screen.getByText('FastAPI 中间件指南')).toBeInTheDocument();
    });
    expect(screen.getByText('Pydantic v2 性能优化')).toBeInTheDocument();
  });

  it('renders NotePanel for the entity', async () => {
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByTestId('note-editor')).toBeInTheDocument();
    });
    expect(screen.getByTestId('note-editor').textContent).toContain('hotspot/h1');
  });

  it('shows type badge in top bar', async () => {
    renderWithRouter();
    await waitFor(() => {
      // type badge 显示 "hotspot"
      expect(screen.getByText('hotspot')).toBeInTheDocument();
    });
  });

  it('shows shared tags in recommendation items', async () => {
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText('#fastapi')).toBeInTheDocument();
    });
    // #python 出现两次 (h2 和 h3 都有)
    expect(screen.getAllByText('#python').length).toBeGreaterThanOrEqual(1);
  });

  it('shows scores in recommendation items', async () => {
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText('★ 2')).toBeInTheDocument();
      expect(screen.getByText('★ 1')).toBeInTheDocument();
    });
  });

  it('renders back button', async () => {
    renderWithRouter();
    expect(screen.getByLabelText('返回首页')).toBeInTheDocument();
  });

  it('displays error on fetch failure', async () => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'not found' }), { status: 404 })
    ) as any;
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText(/请求失败/)).toBeInTheDocument();
    });
  });

  it('loads knowledge items via /api/knowledge/items/{id}', async () => {
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.match(/\/api\/knowledge\/items\/[^/]+$/)) {
        return new Response(
          JSON.stringify({
            item: {
              id: 'k1',
              title: 'FastAPI 概念',
              summary: 'FastAPI 是一个现代 Python web 框架',
              source: 'wiki',
              url: '',
              category: 'ai',
              published_at: '2026-07-22T10:00:00+00:00',
              score: 50,
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (u.match(/\/api\/recommend\/[^/]+\/[^/]+/)) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      if (u.startsWith('/api/annotations')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;

    renderWithRouter('/deep/knowledge/k1');
    await waitFor(() => {
      expect(screen.getByText('FastAPI 概念')).toBeInTheDocument();
    });
  });

  it('shows empty recommendation state when no related items', async () => {
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.match(/\/api\/hotspots\/[^/]+$/)) {
        return new Response(JSON.stringify({ item: mockArticle }), { status: 200 });
      }
      if (u.match(/\/api\/recommend\/[^/]+\/[^/]+/)) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      if (u.startsWith('/api/annotations')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;

    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText('暂无相关条目')).toBeInTheDocument();
    });
  });
});

describe('DeepReadView NotePanel integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn(async (url: any) => {
      const u = typeof url === 'string' ? url : url.url;
      if (u.match(/\/api\/hotspots\/[^/]+$/)) {
        return new Response(JSON.stringify({ item: mockArticle }), { status: 200 });
      }
      if (u.match(/\/api\/recommend\/[^/]+\/[^/]+/)) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      if (u.startsWith('/api/annotations')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }) as any;
  });

  it('calls useAnnotations load on mount', async () => {
    const mockLoad = vi.fn();
    (useAnnotations as any).mockReturnValue({
      items: [],
      loading: false,
      load: mockLoad,
      add: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    });

    renderWithRouter('/deep/hotspot/h1');
    await waitFor(() => {
      expect(mockLoad).toHaveBeenCalledWith('hotspot', 'h1');
    });
  });
});
