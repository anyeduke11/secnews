// frontend/src/components/KnowledgePage.test.tsx
// KnowledgePage 薄壳组件测试 (兼容 App.tsx lazy import)
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';

// Mock fetch: 根据 URL 返回不同 mock 数据
beforeEach(() => {
  globalThis.fetch = vi.fn((url: string) => {
    if (typeof url === 'string' && url.includes('/api/knowledge/graph')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ nodes: [], edges: [] }),
      }) as any;
    }
    if (typeof url === 'string' && url.includes('/api/knowledge/health')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ total_items: 123, total_concepts: 45 }),
      }) as any;
    }
    if (typeof url === 'string' && url.includes('/api/knowledge/items')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [], total: 0 }),
      }) as any;
    }
    if (typeof url === 'string' && url.includes('/api/knowledge/tasks')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [] }),
      }) as any;
    }
    // 默认健康度响应
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ total_items: 0, total_concepts: 0, compiled_count: 0, compiled_ratio: 0, orphan_items: 0, stale_concepts: 0, gap_analysis: [] }),
    }) as any;
  }) as any;
});

// 同步引入子组件, 避免 lazy 在测试中需要 Suspense 解析
import { KnowledgePage } from './KnowledgePage';
import { KnowledgeImport } from './knowledge/KnowledgeImport';
import { KnowledgeProcess } from './knowledge/KnowledgeProcess';
import { KnowledgeCompile } from './knowledge/KnowledgeCompile';
import { KnowledgeCompound } from './knowledge/KnowledgeCompound';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/knowledge" element={<KnowledgePage />}>
          <Route index element={<Navigate to="import" replace />} />
          <Route path="import" element={<KnowledgeImport />} />
          <Route path="process" element={<KnowledgeProcess />} />
          <Route path="compile" element={<KnowledgeCompile />} />
          <Route path="compound" element={<KnowledgeCompound />} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('KnowledgePage (shell)', () => {
  it('renders title and 4 area cards', () => {
    renderAt('/knowledge/import');
    expect(screen.getByText('知识管理')).toBeInTheDocument();
    expect(screen.getByText('信息导入')).toBeInTheDocument();
    expect(screen.getByText('处理数据')).toBeInTheDocument();
    expect(screen.getByText('知识库编译')).toBeInTheDocument();
    expect(screen.getByText('知识复利')).toBeInTheDocument();
  });

  it('renders sub-page content for /knowledge/import', async () => {
    renderAt('/knowledge/import');
    await waitFor(() => {
      expect(screen.getByText('信息导入 · 多源采集入口')).toBeInTheDocument();
    });
  });

  it('renders sub-page content for /knowledge/process', async () => {
    renderAt('/knowledge/process');
    await waitFor(() => {
      // 知识图谱 在 tab chips 和 section header 中都存在, 用 heading 角色筛选
      const heading = screen.getByRole('heading', { name: /知识图谱/ });
      expect(heading).toBeInTheDocument();
    });
  });

  it('fetches /api/knowledge/health for area counts', async () => {
    renderAt('/knowledge/import');
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/knowledge/health');
    });
  });

  it('redirects /knowledge to /knowledge/import via Navigate', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge']}>
        <Routes>
          <Route path="/knowledge" element={<KnowledgePage />}>
            <Route index element={<Navigate to="import" replace />} />
            <Route path="import" element={<KnowledgeImport />} />
          </Route>
        </Routes>
      </MemoryRouter>
    );
    // 跳转后应当看到信息导入 hero
    expect(screen.getByText('信息导入 · 多源采集入口')).toBeInTheDocument();
  });

  it('ignores onBack prop for backward compatibility (uses internal useGoHome)', () => {
    const onBack = vi.fn();
    expect(() =>
      render(
        <MemoryRouter initialEntries={['/knowledge/import']}>
          <Routes>
            <Route path="/knowledge" element={<KnowledgePage onBack={onBack} />}>
              <Route path="import" element={<KnowledgeImport />} />
            </Route>
          </Routes>
        </MemoryRouter>
      )
    ).not.toThrow();
    expect(onBack).not.toHaveBeenCalled();
  });
});
