// frontend/src/components/KnowledgeGraph.test.tsx
// Phase 6 — KnowledgeGraph 节点+边 render + Empty/Loading 测试
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { KnowledgeGraph } from './KnowledgeGraph';
import type { GraphData } from '../types';

describe('KnowledgeGraph', () => {
  beforeEach(() => {
    // 设置必需的 CSS 变量 (useThemeColors 通过 getComputedStyle 读取)
    document.documentElement.style.setProperty('--text-primary', '#eaeaea');
    document.documentElement.style.setProperty('--text-muted', '#888');
    document.documentElement.style.setProperty('--color-security', '#ff6b6b');
    document.documentElement.style.setProperty('--color-ai', '#5b8def');
    document.documentElement.style.setProperty('--color-finance', '#00c96a');
    document.documentElement.style.setProperty('--color-warning', '#f0c929');
    document.documentElement.style.setProperty('--color-startup', '#9b59ff');
    document.documentElement.style.setProperty('--color-info', '#00bcd4');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows loading text initially', () => {
    // 让 fetch 永不 resolve → 保持 loading=true
    globalThis.fetch = vi.fn(() => new Promise(() => {})) as any;
    render(<KnowledgeGraph />);
    expect(screen.getByText(/加载中/)).toBeInTheDocument();
  });

  it('shows empty state when graph data is empty', async () => {
    const emptyData: GraphData = { nodes: [], edges: [] };
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(emptyData),
      } as any)
    ) as any;
    render(<KnowledgeGraph />);
    await waitFor(() => {
      expect(screen.getByText(/暂无概念/)).toBeInTheDocument();
    });
  });

  it('renders ECharts canvas with non-empty data', async () => {
    const data: GraphData = {
      nodes: [
        { id: 'c1', label: '零信任', domain: 'security', count: 5, wiki: 'hotspot' },
        { id: 'c2', label: 'AI Agent', domain: 'ai', count: 8, wiki: 'local' },
      ],
      edges: [
        { source: 'c1', target: 'c2', weight: 2, type: 'related' },
      ],
    };
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(data),
      } as any)
    ) as any;
    const { container } = render(<KnowledgeGraph />);
    // ECharts 渲染为 <div> + <canvas> (jsdom 不一定渲染 canvas, 但容器 div 存在)
    await waitFor(() => {
      // 加载态消失, EmptyState 消失
      expect(screen.queryByText(/加载中/)).not.toBeInTheDocument();
      expect(screen.queryByText(/暂无概念/)).not.toBeInTheDocument();
    });
    // ECharts 容器 style="height: 300px"
    const chartWrapper = container.querySelector('div[style*="height: 300px"]');
    expect(chartWrapper).toBeInTheDocument();
  });

  it('passes domain filter as query param to /api/knowledge/graph', async () => {
    const data: GraphData = { nodes: [], edges: [] };
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(data),
      } as any)
    ) as any;
    globalThis.fetch = fetchMock;
    render(<KnowledgeGraph domain="security" />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/knowledge/graph?domain=security');
    });
  });

  it('handles fetch error gracefully (falls to empty state)', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('network'))) as any;
    render(<KnowledgeGraph />);
    await waitFor(() => {
      // catch 后 setLoading(false), data 仍为空 → 显示 EmptyState
      expect(screen.queryByText(/加载中/)).not.toBeInTheDocument();
    });
  });

  it('handles non-200 response (json returns null/undefined)', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve(null),
      } as any)
    ) as any;
    render(<KnowledgeGraph />);
    await waitFor(() => {
      // null → 回退到 {nodes:[], edges:[]}, 显示 EmptyState
      expect(screen.getByText(/暂无概念/)).toBeInTheDocument();
    });
  });
});
