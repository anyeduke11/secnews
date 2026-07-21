// frontend/src/components/HotspotGrid.test.tsx
// Phase 6 — HotspotGrid 列表+分页+三态测试
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HotspotGrid } from './HotspotGrid';
import type { HotspotItem } from '../types';

const baseItem: HotspotItem = {
  id: 'h1',
  title: 'AI 新闻',
  source: 'aitools',
  url: 'https://example.com/1',
  category: 'ai',
  published_at: '2026-07-21T08:00:00Z',
};

const basePagination = {
  page: 1,
  pageSize: 20,
  totalPages: 1,
  total: 1,
  hasMore: false,
  loadingPage: false,
};

describe('HotspotGrid', () => {
  it('renders an item card', () => {
    render(
      <HotspotGrid
        items={[baseItem]}
        loading={false}
        error={null}
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    expect(screen.getByText('AI 新闻')).toBeInTheDocument();
  });

  it('shows error state when error is set', () => {
    render(
      <HotspotGrid
        items={[]}
        loading={false}
        error="网络失败"
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    expect(screen.getByText('数据加载失败')).toBeInTheDocument();
    expect(screen.getByText('网络失败')).toBeInTheDocument();
  });

  it('shows nothing when loading and no items (LoadingSkeleton 由父级渲染)', () => {
    const { container } = render(
      <HotspotGrid
        items={[]}
        loading={true}
        error={null}
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    // 当前实现: loading=true 时不渲染 items 也不渲染 skeleton
    // (LoadingSkeleton 在 HotspotPage 父级渲染, 不在 Grid 内部)
    // 这里验证不渲染空态/错误态
    expect(screen.queryByText(/暂无热点数据/)).not.toBeInTheDocument();
    expect(screen.queryByText('数据加载失败')).not.toBeInTheDocument();
  });

  it('shows empty state when no items and not loading', () => {
    render(
      <HotspotGrid
        items={[]}
        loading={false}
        error={null}
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    expect(screen.getByText(/暂无热点数据/)).toBeInTheDocument();
  });

  it('clicking favorite calls onToggleFavorite', () => {
    const onToggle = vi.fn();
    render(
      <HotspotGrid
        items={[baseItem]}
        loading={false}
        error={null}
        favoritedIds={new Set()}
        onToggleFavorite={onToggle}
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    fireEvent.click(screen.getByLabelText('收藏'));
    expect(onToggle).toHaveBeenCalledWith(baseItem);
  });

  it('renders pagination controls when totalPages > 1', () => {
    render(
      <HotspotGrid
        items={[baseItem]}
        loading={false}
        error={null}
        {...basePagination}
        totalPages={5}
        total={100}
        hasMore={true}
        onSetPage={vi.fn()}
        onSetPageSize={vi.fn()}
      />
    );
    // 翻页按钮应存在
    expect(screen.getByText(/100 条/)).toBeInTheDocument();
  });

  it('clicking next page calls onSetPage', () => {
    const onSetPage = vi.fn();
    render(
      <HotspotGrid
        items={[baseItem]}
        loading={false}
        error={null}
        {...basePagination}
        page={1}
        totalPages={3}
        hasMore={true}
        onSetPage={onSetPage}
        onSetPageSize={vi.fn()}
      />
    );
    // 找下一页按钮
    const nextBtn = screen.getByLabelText(/下一页/);
    fireEvent.click(nextBtn);
    expect(onSetPage).toHaveBeenCalledWith(2);
  });

  it('page size select calls onSetPageSize', () => {
    const onSetPageSize = vi.fn();
    render(
      <HotspotGrid
        items={[baseItem]}
        loading={false}
        error={null}
        {...basePagination}
        onSetPage={vi.fn()}
        onSetPageSize={onSetPageSize}
      />
    );
    // PAGE_SIZE_OPTIONS = [100, 200, 300, 400]
    const btn100 = screen.getByLabelText('每页 100 条');
    fireEvent.click(btn100);
    expect(onSetPageSize).toHaveBeenCalledWith(100);
  });
});
