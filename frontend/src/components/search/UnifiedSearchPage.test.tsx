/**
 * UnifiedSearchPage — wiki 正文 (chunk) 检索接线测试 (DEV-0241)
 *
 * 测试意图: 后端 chunk 检索能力 (POST /api/wiki/search, FTS5 trigram,
 * 2058 chunks) 此前无任何前端消费方 — 统一搜索页接入后:
 *  - 未选来源时默认同时查 /api/search 与 /api/wiki/search, chunk 命中
 *    以「Wiki 正文」独立分组渲染;
 *  - 「Wiki 正文」来源 chip 可单独勾选;
 *  - chunk 结果的 title 显示 wiki_path, summary 显示正文片段。
 * 全程 mock fetch, 不发真实请求。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { UnifiedSearchPage } from './UnifiedSearchPage';

const SEARCH_FIXTURE = {
  result: {
    query: '勒索软件',
    grouped: {
      hotspot: [
        { entity_type: 'hotspot', entity_id: 'h1', title: '勒索软件态势周报', category: 'security' },
      ],
    },
    items: [
      { entity_type: 'hotspot', entity_id: 'h1', title: '勒索软件态势周报', category: 'security' },
    ],
  },
};

const CHUNKS_FIXTURE = {
  results: [
    { item_id: '2e53d514fba6', chunk_index: 0, snippet: '有关Petya勒索软件，你想知道的都在这里' },
  ],
};

function mockFetch(url: string) {
  if (url.includes('/api/search')) {
    return Promise.resolve(new Response(JSON.stringify(SEARCH_FIXTURE), { status: 200 }));
  }
  if (url.includes('/api/wiki/search')) {
    return Promise.resolve(new Response(JSON.stringify(CHUNKS_FIXTURE), { status: 200 }));
  }
  return Promise.resolve(new Response('{}', { status: 404 }));
}

function renderPage() {
  return render(
    <MemoryRouter>
      <UnifiedSearchPage />
    </MemoryRouter>
  );
}

describe('UnifiedSearchPage — wiki chunk 检索接线', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => mockFetch(String(input))));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('默认搜索合并 chunk 命中为「Wiki 正文」独立分组', async () => {
    renderPage();
    const input = screen.getByPlaceholderText(/搜索热点与知识库/);
    fireEvent.change(input, { target: { value: '勒索软件' } });
    fireEvent.click(screen.getByRole('button', { name: '搜索' }));

    await waitFor(() => {
      // 分组标题 (h3) 形如「Wiki 正文 · 1」; chip 按钮同名, 用 heading 角色区分
      expect(screen.getByRole('heading', { name: /Wiki 正文/ })).toBeInTheDocument();
    });
    // chunk snippet 渲染
    expect(screen.getByText(/Petya勒索软件/)).toBeInTheDocument();
    // 主搜索分组仍在
    expect(screen.getByText('勒索软件态势周报')).toBeInTheDocument();
    // wiki_path 作为 chunk 条目标题
    expect(screen.getByText('items/2e53d514fba6.md')).toBeInTheDocument();
  });

  it('「Wiki 正文」来源 chip 存在且可勾选', () => {
    renderPage();
    const chip = screen.getByRole('button', { name: 'Wiki 正文' });
    fireEvent.click(chip);
    expect(chip).toHaveStyle({ color: 'var(--accent)' });
  });
});
