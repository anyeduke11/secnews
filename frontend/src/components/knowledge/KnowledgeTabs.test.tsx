// frontend/src/components/knowledge/KnowledgeTabs.test.tsx
// 知识管理 4 大领域导航测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { KnowledgeTabs, KNOWLEDGE_AREAS, findAreaByPath } from './KnowledgeTabs';

describe('KnowledgeTabs', () => {
  it('renders all 4 area cards', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/import']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs />} />
        </Routes>
      </MemoryRouter>
    );
    for (const area of KNOWLEDGE_AREAS) {
      expect(screen.getByText(area.title)).toBeInTheDocument();
    }
  });

  it('renders step badges 01/02/03/04 in order', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/import']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('01')).toBeInTheDocument();
    expect(screen.getByText('02')).toBeInTheDocument();
    expect(screen.getByText('03')).toBeInTheDocument();
    expect(screen.getByText('04')).toBeInTheDocument();
  });

  it('highlights active card via data-active', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/process']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs />} />
        </Routes>
      </MemoryRouter>
    );
    const activeCard = document.querySelector('[data-area="process"]');
    expect(activeCard?.getAttribute('data-active')).toBe('true');
    const inactiveCard = document.querySelector('[data-area="import"]');
    expect(inactiveCard?.getAttribute('data-active')).toBe('false');
  });

  it('renders count badge when count provided', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/import']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs counts={{ process: 42 }} />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('omits count badge when count is null/undefined', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/import']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs />} />
        </Routes>
      </MemoryRouter>
    );
    // No count badges should be rendered
    const nav = screen.getByLabelText('知识管理 4 大领域');
    expect(nav.querySelectorAll('span.font-mono.tabular-nums').length).toBe(0);
  });

  it('renders features chips for each area', () => {
    render(
      <MemoryRouter initialEntries={['/knowledge/import']}>
        <Routes>
          <Route path="/knowledge/*" element={<KnowledgeTabs />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText('Cubox 同步')).toBeInTheDocument();
    expect(screen.getByText('知识图谱')).toBeInTheDocument();
    expect(screen.getByText('编译触发')).toBeInTheDocument();
    expect(screen.getByText('学习路径')).toBeInTheDocument();
  });
});

describe('findAreaByPath', () => {
  it('matches exact path', () => {
    expect(findAreaByPath('/knowledge/import').key).toBe('import');
    expect(findAreaByPath('/knowledge/process').key).toBe('process');
    expect(findAreaByPath('/knowledge/compile').key).toBe('compile');
    expect(findAreaByPath('/knowledge/compound').key).toBe('compound');
  });

  it('matches nested sub-paths', () => {
    expect(findAreaByPath('/knowledge/import/something').key).toBe('import');
  });

  it('falls back to first area (import) when no match', () => {
    expect(findAreaByPath('/somewhere/else').key).toBe('import');
    expect(findAreaByPath('/').key).toBe('import');
  });
});

describe('KNOWLEDGE_AREAS meta', () => {
  it('has 4 areas in correct order', () => {
    expect(KNOWLEDGE_AREAS.length).toBe(4);
    expect(KNOWLEDGE_AREAS.map(a => a.key)).toEqual(['import', 'process', 'compile', 'compound']);
    expect(KNOWLEDGE_AREAS.map(a => a.step)).toEqual([1, 2, 3, 4]);
  });

  it('each area has unique accent color', () => {
    const accents = new Set(KNOWLEDGE_AREAS.map(a => a.accentVar));
    expect(accents.size).toBe(4);
  });

  it('each area has path under /knowledge', () => {
    for (const a of KNOWLEDGE_AREAS) {
      expect(a.path.startsWith('/knowledge/')).toBe(true);
    }
  });
});
